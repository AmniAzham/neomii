import io
import re
import pandas as pd
import streamlit as st

from database import (
    get_products,
    add_product,
    get_product_materials,
    get_shopee_mappings,
    save_shopee_mapping,
    shopee_line_already_imported,
    import_shopee_sale,
)


FABRIC_CATEGORIES = {
    "Outer Fabric", "Lining Fabric", "Fabric", "Batting", "Interfacing"
}
LENGTH_CATEGORIES = {"Elastic", "Velcro", "Ribbon"}


def _norm(value):
    value = "" if value is None else str(value)
    value = value.strip().lower()
    value = re.sub(r"\s+", " ", value)
    return value


def _base_variation(value):
    """Remove common Shopee size suffixes such as ',S' for matching only."""
    value = "" if pd.isna(value) else str(value).strip()
    return re.sub(r"\s*,\s*(s|m|l|xl|xxl)\s*$", "", value, flags=re.I).strip()


def _modal_per_unit(product_id):
    recipes = get_product_materials(product_id)
    material_cost = 0.0

    for recipe in recipes:
        category = recipe["material_category"]
        unit_price = float(
            recipe["unit_price"]
            if "unit_price" in recipe.keys() and recipe["unit_price"] is not None
            else recipe["average_unit_cost"] or 0
        )

        if category in FABRIC_CATEGORIES:
            yield_per_metre = float(recipe["yield_per_metre"] or 0)
            if yield_per_metre > 0:
                material_cost += unit_price / yield_per_metre
        else:
            material_cost += unit_price * float(recipe["quantity_used"] or 0)

    products = get_products()
    product = next((p for p in products if int(p["id"]) == int(product_id)), None)
    if not product:
        return material_cost

    return (
        material_cost
        + float(product["packaging_cost"] or 0)
        + float(product["platform_fee"] or 0)
    )


def _read_upload(uploaded):
    name = uploaded.name.lower()
    raw = uploaded.getvalue()

    if name.endswith(".csv"):
        return pd.read_csv(io.BytesIO(raw))

    if name.endswith(".xlsx") or name.endswith(".xls"):
        return pd.read_excel(io.BytesIO(raw), sheet_name="orders")

    raise ValueError("Please upload a Shopee .xlsx, .xls or .csv export.")


def _prepare(df):
    required = [
        "Order ID",
        "Order Status",
        "Product Name",
        "Variation Name",
        "Deal Price",
        "Quantity",
        "Returned quantity",
        "Order Creation Date",
    ]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(
            "This file does not look like the expected Shopee order export. "
            "Missing columns: " + ", ".join(missing)
        )

    out = df.copy()
    out["Variation Name"] = out["Variation Name"].fillna("")
    out["Returned quantity"] = pd.to_numeric(
        out["Returned quantity"], errors="coerce"
    ).fillna(0)
    out["Quantity"] = pd.to_numeric(out["Quantity"], errors="coerce").fillna(0)
    out["Net Quantity"] = (
        out["Quantity"] - out["Returned quantity"]
    ).clip(lower=0).astype(int)

    out["Deal Price"] = pd.to_numeric(out["Deal Price"], errors="coerce").fillna(0)
    out["Order Creation Date"] = pd.to_datetime(
        out["Order Creation Date"], errors="coerce"
    )

    # Keep completed/received orders, but exclude rows with no net sold quantity.
    bad_status_words = ("cancel", "refund", "return")
    out["Importable Status"] = ~out["Order Status"].fillna("").str.lower().apply(
        lambda x: any(word in x for word in bad_status_words)
    )
    out = out[
        (out["Net Quantity"] > 0)
        & out["Importable Status"]
        & out["Order Creation Date"].notna()
    ].copy()

    # Stable duplicate key. Handles multiple product lines within one Shopee order.
    out["_line_key"] = (
        out["Order ID"].astype(str).str.strip()
        + "|"
        + out["Product Name"].astype(str).str.strip()
        + "|"
        + out["Variation Name"].astype(str).str.strip()
    )
    return out


def _mapping_key(product_name, variation_name):
    return (_norm(product_name), _norm(variation_name))


def _suggest_product(shopee_product_name, shopee_variation, products):
    variation = _norm(_base_variation(shopee_variation))
    if not variation:
        return None

    exact = [p for p in products if _norm(p["design"]) == variation]
    if len(exact) == 1:
        return exact[0]

    # If duplicate design names exist, use Shopee listing wording as a category hint.
    listing = _norm(shopee_product_name)
    if len(exact) > 1:
        if "kindle" in listing or "boox" in listing:
            hinted = [p for p in exact if "kindle" in _norm(p["category"])]
            if len(hinted) == 1:
                return hinted[0]
        if "book sleeve" in listing:
            hinted = [p for p in exact if "book" in _norm(p["category"])]
            if len(hinted) == 1:
                return hinted[0]

    return None



HISTORICAL_BOOK_SLEEVE_DESIGN = "Historical / Discontinued Book Sleeve"


def _ensure_historical_book_sleeve():
    """
    Create ONE generic discontinued Book Sleeve record for old Shopee designs.
    This avoids manually creating every discontinued design.
    """
    products = get_products()

    for p in products:
        if (
            _norm(p["category"]) == "book sleeve"
            and _norm(p["design"]) == _norm(HISTORICAL_BOOK_SLEEVE_DESIGN)
        ):
            return int(p["id"])

    add_product(
        category="Book Sleeve",
        design=HISTORICAL_BOOK_SLEEVE_DESIGN,
        sku="HIST-BOOK-SLEEVE",
        selling_price=0,
        packaging_cost=0,
        platform_fee=0,
        stock=0,
        image_path=None,
        status="Discontinued"
    )

    products = get_products()
    for p in products:
        if (
            _norm(p["category"]) == "book sleeve"
            and _norm(p["design"]) == _norm(HISTORICAL_BOOK_SLEEVE_DESIGN)
        ):
            return int(p["id"])

    return None


def show_shopee_import_page():
    st.subheader("Shopee Import")
    st.write(
        "Import historical Shopee Book Sleeve orders into Neomii. "
        "Current Book Sleeve designs can be mapped normally. "
        "Old discontinued Book Sleeve designs can all be mapped to one historical record. "
        "Items outside the Book Sleeve scope can be ignored. "
        "By default this does **not** deduct your current finished stock."
    )

    st.info(
        "For your existing Shopee history, leave stock deduction OFF because "
        "those sales are already reflected in your current inventory."
    )

    uploaded = st.file_uploader(
        "Upload Shopee order export",
        type=["xlsx", "xls", "csv"],
        key="shopee_order_upload"
    )

    if uploaded is None:
        st.caption(
            "Shopee Seller Centre exports normally contain columns such as "
            "Order ID, Product Name, Variation Name, Deal Price and Quantity."
        )
        return

    try:
        raw_df = _read_upload(uploaded)
        df = _prepare(raw_df)
    except Exception as exc:
        st.error(str(exc))
        return

    if df.empty:
        st.warning("No importable sales were found in this file.")
        return

    historical_product_id = _ensure_historical_book_sleeve()

    products = get_products()
    if not products:
        st.warning("Add your Neomii products first.")
        return

    existing_mappings = {
        _mapping_key(m["shopee_product_name"], m["shopee_variation_name"]):
            int(m["product_id"])
        for m in get_shopee_mappings()
    }

    unique_items = (
        df[["Product Name", "Variation Name"]]
        .drop_duplicates()
        .sort_values(["Product Name", "Variation Name"])
        .reset_index(drop=True)
    )

    product_by_id = {int(p["id"]): p for p in products}
    product_labels = {}
    for p in products:
        pid = int(p["id"])
        if pid == historical_product_id:
            product_labels[pid] = "📦 Historical / Discontinued Book Sleeve"
        else:
            product_labels[pid] = (
                f"{p['category']} — {p['design']}"
                + (f" [{p['sku']}]" if p["sku"] else "")
            )

    st.markdown("### 1. Match Shopee items to Neomii products")
    st.caption(
        "Neomii will suggest exact design-name matches. "
        "For an old Book Sleeve design you no longer sell, choose "
        "📦 Historical / Discontinued Book Sleeve. Neomii remembers the mapping."
    )

    chosen = {}
    all_mapped = True

    for idx, row in unique_items.iterrows():
        shop_product = str(row["Product Name"]).strip()
        shop_variation = str(row["Variation Name"]).strip()
        key = _mapping_key(shop_product, shop_variation)

        default_id = existing_mappings.get(key)
        if default_id not in product_by_id:
            suggested = _suggest_product(shop_product, shop_variation, products)
            default_id = int(suggested["id"]) if suggested else None

        IGNORE = -1

        normal_product_ids = [
            int(p["id"])
            for p in products
            if int(p["id"]) != historical_product_id
        ]

        options = [None]
        if historical_product_id is not None:
            options.append(historical_product_id)
        options.append(IGNORE)
        options.extend(normal_product_ids)
        default_index = options.index(default_id) if default_id in options else 0

        short_listing = shop_product
        if len(short_listing) > 70:
            short_listing = short_listing[:67] + "..."

        label = f"{short_listing}  |  Variation: {shop_variation or '(none)'}"

        selected_id = st.selectbox(
            label,
            options,
            index=default_index,
            format_func=lambda x: (
                "— Select Neomii product —"
                if x is None
                else "🚫 Ignore / Outside Book Sleeve scope"
                if x == IGNORE
                else "📦 Historical / Discontinued Book Sleeve"
                if x == historical_product_id
                else product_labels[x]
            ),
            key=f"shopee_map_{idx}_{abs(hash(key))}"
        )

        chosen[key] = selected_id
        if selected_id is None:
            all_mapped = False

    if st.button(
        "💾 Save Product Mappings",
        disabled=not all_mapped,
        key="save_shopee_mappings"
    ):
        errors = []
        for _, row in unique_items.iterrows():
            shop_product = str(row["Product Name"]).strip()
            shop_variation = str(row["Variation Name"]).strip()
            key = _mapping_key(shop_product, shop_variation)
            selected_id = chosen[key]
            if selected_id == -1:
                continue
            ok, err = save_shopee_mapping(
                shop_product,
                shop_variation,
                selected_id
            )
            if not ok:
                errors.append(err)

        if errors:
            st.error("Some mappings could not be saved: " + "; ".join(errors))
        else:
            st.success("Mappings saved.")

    st.info(
        "Use 📦 Historical / Discontinued Book Sleeve for old Book Sleeve designs. "
        "They will still count toward historical Book Sleeve demand for forecasting, "
        "without creating every old design in your product list."
    )

    st.divider()
    st.markdown("### 2. Import Preview")

    preview_rows = []
    ready_count = 0
    duplicate_count = 0
    ignored_count = 0
    unmapped_count = 0

    for _, row in df.iterrows():
        key = _mapping_key(row["Product Name"], row["Variation Name"])
        product_id = chosen.get(key)
        duplicate = shopee_line_already_imported(row["_line_key"])

        if product_id == -1:
            status = "Ignored / Outside scope"
            ignored_count += 1
        elif duplicate:
            status = "Already imported"
            duplicate_count += 1
        elif product_id is None:
            status = "Needs mapping"
            unmapped_count += 1
        else:
            status = "Ready"
            ready_count += 1

        preview_rows.append({
            "Order Date": row["Order Creation Date"].strftime("%Y-%m-%d"),
            "Order ID": row["Order ID"],
            "Shopee Variation": row["Variation Name"] or "(none)",
            "Neomii Product": (
                "Ignored"
                if product_id == -1
                else "📦 Historical / Discontinued Book Sleeve"
                if product_id == historical_product_id
                else product_labels.get(product_id, "Not mapped")
                if product_id else "Not mapped"
            ),
            "Qty": int(row["Net Quantity"]),
            "Price": f"RM {float(row['Deal Price']):.2f}",
            "Status": status,
        })

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Ready to Import", ready_count)
    c2.metric("Already Imported", duplicate_count)
    c3.metric("Ignored", ignored_count)
    c4.metric("Needs Mapping", unmapped_count)

    st.dataframe(
        pd.DataFrame(preview_rows),
        use_container_width=True,
        hide_index=True
    )

    deduct_stock = st.checkbox(
        "Deduct current finished stock during import",
        value=False,
        key="shopee_import_deduct_stock",
        help=(
            "Leave this OFF for historical orders that are already reflected "
            "in your current inventory."
        )
    )

    if deduct_stock:
        st.warning(
            "Stock deduction is ON. Only use this if these Shopee orders have "
            "NOT already been deducted from your current Neomii stock."
        )

    can_import = ready_count > 0 and unmapped_count == 0

    if st.button(
        "📥 Import Shopee Sales",
        type="primary",
        disabled=not can_import,
        key="run_shopee_import"
    ):
        # Save mappings first.
        for _, row in unique_items.iterrows():
            key = _mapping_key(row["Product Name"], row["Variation Name"])
            if chosen[key] != -1:
                save_shopee_mapping(
                    str(row["Product Name"]).strip(),
                    str(row["Variation Name"]).strip(),
                    chosen[key]
                )

        imported = 0
        skipped = 0
        errors = []

        for _, row in df.iterrows():
            key = _mapping_key(row["Product Name"], row["Variation Name"])
            product_id = chosen.get(key)

            if product_id is None or product_id == -1:
                skipped += 1
                continue

            if shopee_line_already_imported(row["_line_key"]):
                skipped += 1
                continue

            modal = _modal_per_unit(product_id)

            ok, result = import_shopee_sale(
                product_id=product_id,
                quantity_sold=int(row["Net Quantity"]),
                selling_price_per_unit=float(row["Deal Price"]),
                modal_per_unit=modal,
                sold_at=row["Order Creation Date"].strftime("%Y-%m-%d %H:%M:%S"),
                external_order_id=str(row["Order ID"]),
                external_line_key=row["_line_key"],
                deduct_stock=deduct_stock
            )

            if ok:
                imported += 1
            elif result == "Already imported":
                skipped += 1
            else:
                errors.append(f"{row['Order ID']}: {result}")

        if errors:
            st.error(
                f"Imported {imported} sale line(s), skipped {skipped}. "
                f"{len(errors)} error(s): " + "; ".join(errors[:5])
            )
        else:
            st.success(
                f"Imported {imported} Shopee sale line(s). "
                f"Skipped {skipped} duplicate/existing line(s)."
            )
            st.rerun()
