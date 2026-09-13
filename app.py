import os
import pandas as pd
import streamlit as st

from production import show_production_page
from sales import show_sales_page

from database import (
    initialize_database,
    add_material,
    get_materials,
    update_material,
    restock_material,
    get_restock_history,
    delete_material,
    add_product,
    get_products,
    update_product,
    delete_product,
    add_product_material,
    get_product_materials,
    update_product_material_yield,
    delete_product_material,
    get_shop_settings,
    update_shop_settings
)

# ============================================================
# SETUP
# ============================================================

initialize_database()

os.makedirs("product_images", exist_ok=True)
os.makedirs("assets", exist_ok=True)

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_LOGO_PATH = os.path.join(APP_DIR, "assets", "neomii_logo.png")

st.set_page_config(
    page_title="Neomii",
    page_icon=DEFAULT_LOGO_PATH if os.path.exists(DEFAULT_LOGO_PATH) else None,
    layout="wide"
)

# ============================================================
# MATERIAL LOGIC
# ============================================================

CUT_CATEGORIES = {
    "Outer Fabric",
    "Lining Fabric",
    "Fabric",
    "Batting",
    "Interfacing"
}

LENGTH_CATEGORIES = {
    "Elastic",
    "Velcro",
    "Ribbon"
}

UNIT_CATEGORIES = {
    "Button",
    "Zipper",
    "Label",
    "Packaging",
    "Thread",
    "Other"
}


def method_for_category(category):
    # Internal calculation behaviour only.
    # The seller never needs to choose or see a material type.
    if category in CUT_CATEGORIES:
        return "area"
    if category in LENGTH_CATEGORIES:
        return "length"
    return "count"



# ============================================================
# COST CALCULATIONS
# ============================================================

def calculate_recipe_item_cost(recipe):
    category = recipe["material_category"]
    method = method_for_category(category)

    unit_price = float(
        recipe["unit_price"]
        if "unit_price" in recipe.keys() and recipe["unit_price"] is not None
        else recipe["average_unit_cost"] or 0
    )

    # Fabric-like materials are costed using REAL CUTTING YIELD.
    # Example: RM14 per metre / 7 Book Sleeves = RM2 per Book Sleeve.
    if method == "area":
        yield_per_metre = float(
            recipe["yield_per_metre"]
            if "yield_per_metre" in recipe.keys()
            and recipe["yield_per_metre"] is not None
            else 0
        )

        if yield_per_metre <= 0:
            return 0.0

        return unit_price / yield_per_metre

    if method == "length":
        return unit_price * float(recipe["quantity_used"] or 0)

    return unit_price * float(recipe["quantity_used"] or 0)


def calculate_product_material_cost(product_id):
    recipes = get_product_materials(product_id)

    total = 0

    for recipe in recipes:
        total += calculate_recipe_item_cost(recipe)

    return total


def recipe_usage_text(recipe):
    """Return a seller-friendly description of how cost is calculated."""
    method = method_for_category(recipe["material_category"])

    if method == "area":
        pieces = int(recipe["pieces_count"] or 0)
        width = float(recipe["piece_width_cm"] or 0)
        height = float(recipe["piece_height_cm"] or 0)
        yield_per_metre = float(
            recipe["yield_per_metre"]
            if "yield_per_metre" in recipe.keys()
            and recipe["yield_per_metre"] is not None
            else 0
        )

        size_text = (
            f"{pieces} piece(s) × {width:g} × {height:g} cm"
            if pieces > 0 and width > 0 and height > 0
            else "Dimensions saved for reference"
        )

        if yield_per_metre > 0:
            return f"{size_text} | Real yield: {yield_per_metre:g} per metre"

        return f"{size_text} | Real yield not set"

    if method == "length":
        centimetres = float(recipe["quantity_used"] or 0) * 100
        return f"{centimetres:g} cm used"

    quantity = float(recipe["quantity_used"] or 0)
    unit = recipe["unit"] or "piece"
    return f"{quantity:g} {unit}(s) used"


def show_modal_breakdown(product):
    """Display exactly what makes up the modal for one product."""
    recipes = get_product_materials(product["id"])

    material_rows = []
    material_total = 0.0

    for recipe in recipes:
        item_cost = calculate_recipe_item_cost(recipe)
        material_total += item_cost
        method = method_for_category(recipe["material_category"])
        if method == "area":
            unit_price = float(
                recipe["unit_price"]
                if "unit_price" in recipe.keys() and recipe["unit_price"] is not None
                else recipe["average_unit_cost"] or 0
            )
            yield_per_metre = float(recipe["yield_per_metre"] or 0)
            calculation = (
                f"RM {unit_price:.2f}/m ÷ {yield_per_metre:g}"
                if yield_per_metre > 0
                else "Set real yield"
            )
        else:
            calculation = recipe_usage_text(recipe)

        material_rows.append({
            "Item": recipe["material_name"],
            "Recipe / Yield": recipe_usage_text(recipe),
            "Calculation": calculation,
            "Cost (RM)": round(item_cost, 2),
        })

    packaging_cost = float(product["packaging_cost"] or 0)
    platform_fee = float(product["platform_fee"] or 0)
    total_modal = material_total + packaging_cost + platform_fee
    selling_price = float(product["selling_price"] or 0)
    profit = selling_price - total_modal

    if material_rows:
        st.markdown("**Materials**")
        st.dataframe(
            pd.DataFrame(material_rows),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No materials have been added to this product recipe yet.")

    other_rows = []
    if packaging_cost > 0:
        other_rows.append({"Item": "Packaging", "Cost (RM)": round(packaging_cost, 2)})
    if platform_fee > 0:
        other_rows.append({"Item": "Platform fee", "Cost (RM)": round(platform_fee, 2)})

    if other_rows:
        st.markdown("**Other costs**")
        st.dataframe(
            pd.DataFrame(other_rows),
            use_container_width=True,
            hide_index=True,
        )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Materials", f"RM {material_total:.2f}")
    c2.metric("Other costs", f"RM {packaging_cost + platform_fee:.2f}")
    c3.metric("Total modal", f"RM {total_modal:.2f}")
    c4.metric("Profit / unit", f"RM {profit:.2f}")

    st.caption(
        f"RM {material_total:.2f} materials + "
        f"RM {packaging_cost:.2f} packaging + "
        f"RM {platform_fee:.2f} platform fee = "
        f"RM {total_modal:.2f} total modal"
    )


# ============================================================
# HEADER
# ============================================================

settings = get_shop_settings()

shop_name = "Neomii"
logo_path = None

if settings:
    shop_name = settings["shop_name"]
    logo_path = settings["logo_path"]

col_logo, col_title = st.columns([1, 6])

with col_logo:
    if logo_path:
        full_logo_path = (
            logo_path
            if os.path.isabs(logo_path)
            else os.path.join(APP_DIR, logo_path)
        )

        if os.path.exists(full_logo_path):
            st.image(full_logo_path, width=90)

with col_title:
    st.title(shop_name)
    st.caption("Inventory • Costs • Sales")

st.divider()

# ============================================================
# TABS
# ============================================================

(
    dashboard_tab,
    materials_tab,
    products_tab,
    recipe_tab,
    production_tab,
    sales_tab,
    settings_tab
) = st.tabs([
    " Dashboard",
    " Materials",
    " Products",
    " Product Recipe",
    " Production",
    " Sales",
    " Settings"
])

# ============================================================
# DASHBOARD
# ============================================================

with dashboard_tab:
    st.subheader("Business Overview")

    products = get_products()
    materials = get_materials()

    total_products = len(products)
    total_finished_stock = sum(
        int(product["stock"] or 0)
        for product in products
    )

    modal_in_stock = 0
    potential_profit = 0

    for product in products:
        material_cost = calculate_product_material_cost(
            product["id"]
        )

        total_unit_cost = (
            material_cost
            + float(product["packaging_cost"] or 0)
            + float(product["platform_fee"] or 0)
        )

        profit = (
            float(product["selling_price"] or 0)
            - total_unit_cost
        )

        modal_in_stock += (
            total_unit_cost
            * int(product["stock"] or 0)
        )

        potential_profit += (
            profit
            * int(product["stock"] or 0)
        )

    col1, col2, col3, col4 = st.columns(4)

    col1.metric(
        "Product Designs",
        total_products
    )

    col2.metric(
        "Finished Stock",
        total_finished_stock
    )

    col3.metric(
        "Modal in Finished Stock",
        f"RM {modal_in_stock:.2f}"
    )

    col4.metric(
        "Potential Profit",
        f"RM {potential_profit:.2f}"
    )

    st.divider()

    st.subheader("Current Materials")

    if not materials:
        st.info("No materials added yet.")
    else:
        low_stock_count = sum(
            1
            for material in materials
            if float(material["current_quantity"] or 0) <= 0
        )

        col1, col2 = st.columns(2)

        col1.metric(
            "Materials Tracked",
            len(materials)
        )

        col2.metric(
            "Out of Stock",
            low_stock_count
        )

    st.divider()

    st.subheader("Product Overview")

    if not products:
        st.info("No products added yet.")

    else:
        # Compact 2-column product gallery
        for row_start in range(0, len(products), 2):
            row_products = products[row_start:row_start + 2]
            card_cols = st.columns(2, gap="medium")

            for col, product in zip(card_cols, row_products):
                with col:
                    material_cost = calculate_product_material_cost(product["id"])

                    total_cost = (
                        material_cost
                        + float(product["packaging_cost"] or 0)
                        + float(product["platform_fee"] or 0)
                    )

                    profit = float(product["selling_price"] or 0) - total_cost

                    with st.container(border=True):
                        # Product photo
                        image_path = product["image_path"]

                        if image_path:
                            image_path = image_path.replace("\\", "/")
                            full_image_path = os.path.join(
                                os.path.dirname(os.path.abspath(__file__)),
                                image_path
                            )

                            if os.path.exists(full_image_path):
                                with open(full_image_path, "rb") as image_file:
                                    image_bytes = image_file.read()
                                st.image(
                                    image_bytes,
                                    use_container_width=True
                                )
                            else:
                                st.markdown(
                                    "<div style='height:170px;display:flex;align-items:center;justify-content:center;'></div>",
                                    unsafe_allow_html=True
                                )
                        else:
                            st.markdown(
                                "<div style='height:170px;display:flex;align-items:center;justify-content:center;'></div>",
                                unsafe_allow_html=True
                            )

                        st.write(f"**{product['design']}**")
                        st.caption(product["category"])

                        if product["sku"]:
                            st.caption(f"SKU: {product['sku']}")

                        metric1, metric2 = st.columns(2)
                        metric1.metric(
                            "Stock",
                            int(product["stock"] or 0)
                        )
                        metric2.metric(
                            "Price",
                            f"RM {float(product['selling_price'] or 0):.2f}"
                        )

                        metric3, metric4 = st.columns(2)
                        metric3.metric(
                            "Modal",
                            f"RM {total_cost:.2f}"
                        )
                        metric4.metric(
                            "Profit",
                            f"RM {profit:.2f}"
                        )

# ============================================================
# MATERIALS
# ============================================================

with materials_tab:
    st.subheader("Materials Library")

    st.write(
        "Save the normal price for each material first. "
        "Inventory is separate — use Restock to record how much you actually have."
    )

    st.info(
        "Example: Pink Bunny Fabric = RM24 per metre, width 150 cm. "
        "If you restock 0.5 m, that means 50 cm long × 150 cm wide."
    )

    # --------------------------------------------------------
    # ADD MATERIAL
    # --------------------------------------------------------

    with st.expander(" Add New Material", expanded=True):
        material_name = st.text_input(
            "Material Name",
            placeholder="Example: Pink Bunny Fabric",
            key="new_material_name"
        )

        category = st.selectbox(
            "Material Category",
            [
                "Outer Fabric",
                "Lining Fabric",
                "Fabric",
                "Batting",
                "Interfacing",
                "Button",
                "Elastic",
                "Zipper",
                "Velcro",
                "Ribbon",
                "Label",
                "Packaging",
                "Thread",
                "Other"
            ],
            key="new_material_category"
        )

        method = method_for_category(category)

        if method in ["area", "length"]:
            unit = "metre"
            price_label = "Price per Metre (RM)"
            price_step = 0.50
        else:
            unit = st.selectbox(
                "Sold / Costed Per",
                ["piece", "unit", "set"],
                key="new_material_unit"
            )
            price_label = f"Price per {unit.title()} (RM)"
            price_step = 0.10

        unit_price = st.number_input(
            price_label,
            min_value=0.0,
            step=price_step,
            key="new_material_unit_price"
        )

        fabric_width = 0.0

        if method == "area":
            fabric_width = st.number_input(
                "Material Width (cm)",
                min_value=0.0,
                step=1.0,
                value=150.0,
                key="new_material_width"
            )

            if unit_price > 0 and fabric_width > 0:
                st.caption(
                    f"1 metre = 100 cm × {fabric_width:g} cm "
                    f"= {100 * fabric_width:,.0f} cm²."
                )

        elif method == "length":
            st.caption(
                "Enter the price for one full metre."
            )

        else:
            st.caption(
                "Enter the cost of one individual piece/unit. "
                "Stock quantity is added later under Restock."
            )

        if st.button(
            "Save Material",
            type="primary",
            key="save_material"
        ):
            if not material_name.strip():
                st.error("Please enter a material name.")
            elif unit_price <= 0:
                st.error("Please enter the price.")
            elif method == "area" and fabric_width <= 0:
                st.error("Please enter the material width.")
            else:
                add_material(
                    material_name.strip(),
                    category,
                    unit_price,
                    unit,
                    fabric_width
                )

                st.success(
                    "Material saved. Current stock starts at 0."
                )
                st.rerun()

    # --------------------------------------------------------
    # SAVED MATERIALS
    # --------------------------------------------------------

    st.divider()
    st.subheader("Saved Materials")

    materials = get_materials()

    if not materials:
        st.info("No materials saved yet.")

    else:
        for material in materials:
            method = method_for_category(material["category"])
            current_stock = float(material["current_quantity"] or 0)

            unit_price = float(
                material["unit_price"]
                if "unit_price" in material.keys()
                and material["unit_price"] is not None
                else material["average_unit_cost"] or 0
            )

            with st.container(border=True):
                col1, col2, col3 = st.columns([4, 3, 3])

                with col1:
                    st.write(f"**{material['name']}**")
                    st.caption(material["category"])

                with col2:
                    if method in ["area", "length"]:
                        st.write(f"Price: **RM {unit_price:.2f}/m**")
                        st.write(f"Current stock: **{current_stock:.2f} m**")
                    else:
                        display_unit = material["unit"] or "piece"
                        st.write(f"Price: **RM {unit_price:.2f}/{display_unit}**")
                        st.write(
                            f"Current stock: **{current_stock:g} {display_unit}**"
                        )

                with col3:
                    if method == "area":
                        width = float(material["fabric_width_cm"] or 0)
                        st.write(f"Width: **{width:g} cm**")

                        if width > 0 and current_stock > 0:
                            stock_length_cm = current_stock * 100
                            stock_area = stock_length_cm * width

                            st.caption(
                                f"{current_stock:g} m = "
                                f"{stock_length_cm:g} cm long × "
                                f"{width:g} cm wide "
                                f"({stock_area:,.0f} cm²)"
                            )

        # ----------------------------------------------------
        # MANAGE MATERIAL
        # ----------------------------------------------------

        st.divider()
        st.subheader("Manage Material")

        material_options = {
            f"{m['name']} — {m['category']}": m
            for m in materials
        }

        selected_material_name = st.selectbox(
            "Select Material",
            list(material_options.keys()),
            key="manage_material_select"
        )

        selected_material = material_options[selected_material_name]

        edit_tab, restock_tab, history_tab = st.tabs([
            " Edit Price / Material",
            " Restock Inventory",
            " Restock History"
        ])

        # ----------------------------------------------------
        # EDIT
        # ----------------------------------------------------

        with edit_tab:
            edit_name = st.text_input(
                "Material Name",
                value=selected_material["name"],
                key=f"edit_name_{selected_material['id']}"
            )

            categories = [
                "Outer Fabric",
                "Lining Fabric",
                "Fabric",
                "Batting",
                "Interfacing",
                "Button",
                "Elastic",
                "Zipper",
                "Velcro",
                "Ribbon",
                "Label",
                "Packaging",
                "Thread",
                "Other"
            ]

            current_category = selected_material["category"]
            category_index = (
                categories.index(current_category)
                if current_category in categories
                else 0
            )

            edit_category = st.selectbox(
                "Material Category",
                categories,
                index=category_index,
                key=f"edit_category_{selected_material['id']}"
            )

            edit_method = method_for_category(edit_category)

            if edit_method in ["area", "length"]:
                edit_unit = "metre"
                edit_price_label = "Price per Metre (RM)"
            else:
                units = ["piece", "unit", "set"]
                current_unit = selected_material["unit"] or "piece"
                unit_index = (
                    units.index(current_unit)
                    if current_unit in units
                    else 0
                )

                edit_unit = st.selectbox(
                    "Sold / Costed Per",
                    units,
                    index=unit_index,
                    key=f"edit_unit_{selected_material['id']}"
                )

                edit_price_label = (
                    f"Price per {edit_unit.title()} (RM)"
                )

            current_unit_price = float(
                selected_material["unit_price"]
                if "unit_price" in selected_material.keys()
                and selected_material["unit_price"] is not None
                else selected_material["average_unit_cost"] or 0
            )

            edit_unit_price = st.number_input(
                edit_price_label,
                min_value=0.0,
                value=current_unit_price,
                step=0.10,
                key=f"edit_price_{selected_material['id']}"
            )

            edit_width = 0.0

            if edit_method == "area":
                edit_width = st.number_input(
                    "Material Width (cm)",
                    min_value=0.0,
                    value=float(
                        selected_material["fabric_width_cm"] or 0
                    ),
                    step=1.0,
                    key=f"edit_width_{selected_material['id']}"
                )

            if edit_method in ["area", "length"]:
                edit_current_quantity = st.number_input(
                    "Current Stock (metre)",
                    min_value=0.0,
                    value=float(
                        selected_material["current_quantity"] or 0
                    ),
                    step=0.1,
                    key=f"edit_stock_{selected_material['id']}"
                )
            else:
                edit_current_quantity = st.number_input(
                    f"Current Stock ({edit_unit})",
                    min_value=0.0,
                    value=float(
                        selected_material["current_quantity"] or 0
                    ),
                    step=1.0,
                    key=f"edit_stock_{selected_material['id']}"
                )

            st.caption(
                "The price here is what Neomii uses for modal calculations. "
                "Restocking does not change this price."
            )

            col_save, col_delete = st.columns(2)

            with col_save:
                if st.button(
                    "Save Changes",
                    type="primary",
                    key=f"save_edit_material_{selected_material['id']}"
                ):
                    if edit_unit_price <= 0:
                        st.error("Price must be more than zero.")
                    elif edit_method == "area" and edit_width <= 0:
                        st.error("Material width must be more than zero.")
                    else:
                        update_material(
                            selected_material["id"],
                            edit_name,
                            edit_category,
                            edit_unit,
                            edit_width,
                            edit_current_quantity,
                            edit_unit_price
                        )

                        st.success("Material updated.")
                        st.rerun()

            with col_delete:
                if st.button(
                    "Delete Material",
                    key=f"delete_material_{selected_material['id']}"
                ):
                    delete_material(selected_material["id"])
                    st.rerun()

        # ----------------------------------------------------
        # RESTOCK
        # ----------------------------------------------------

        with restock_tab:
            selected_method = method_for_category(
                selected_material["category"]
            )

            if selected_method in ["area", "length"]:
                quantity_label = "Add Stock (metre)"
                display_unit = "m"
                quantity_step = 0.1
            else:
                display_unit = selected_material["unit"] or "piece"
                quantity_label = f"Add Stock ({display_unit})"
                quantity_step = 1.0

            quantity_added = st.number_input(
                quantity_label,
                min_value=0.0,
                step=quantity_step,
                key=f"restock_qty_{selected_material['id']}"
            )

            old_quantity = float(
                selected_material["current_quantity"] or 0
            )

            if quantity_added > 0:
                new_total = old_quantity + quantity_added

                st.success(
                    f"{old_quantity:g} {display_unit} + "
                    f"{quantity_added:g} {display_unit} = "
                    f"**{new_total:g} {display_unit} after restock**"
                )

                if selected_method == "area":
                    width = float(
                        selected_material["fabric_width_cm"] or 0
                    )

                    added_length_cm = quantity_added * 100
                    added_area = added_length_cm * width

                    st.caption(
                        f"{quantity_added:g} m = "
                        f"{added_length_cm:g} cm long × "
                        f"{width:g} cm wide = "
                        f"{added_area:,.0f} cm² added."
                    )

            st.caption(
                "Restock changes inventory only. "
                "The material price stays unchanged."
            )

            if st.button(
                "Add Stock",
                type="primary",
                key=f"restock_button_{selected_material['id']}"
            ):
                if quantity_added <= 0:
                    st.error("Enter how much stock you are adding.")
                else:
                    restock_material(
                        selected_material["id"],
                        quantity_added
                    )

                    st.success("Inventory updated.")
                    st.rerun()

        # ----------------------------------------------------
        # HISTORY
        # ----------------------------------------------------

        with history_tab:
            history = get_restock_history(
                selected_material["id"]
            )

            if not history:
                st.info("No restock history recorded yet.")
            else:
                selected_method = method_for_category(
                    selected_material["category"]
                )

                display_unit = (
                    "m"
                    if selected_method in ["area", "length"]
                    else selected_material["unit"] or "piece"
                )

                history_data = []

                for item in history:
                    history_data.append({
                        "Date": item["purchased_at"],
                        f"Stock Added ({display_unit})": item["quantity_added"],
                        "Price Reference": (
                            f"RM {float(item['unit_cost'] or 0):.2f}/{display_unit}"
                        )
                    })

                st.dataframe(
                    pd.DataFrame(history_data),
                    use_container_width=True,
                    hide_index=True
                )


# ============================================================
# PRODUCTS
# ============================================================

with products_tab:
    st.subheader("Products")

    # --------------------------------------------------------
    # ADD PRODUCT
    # --------------------------------------------------------

    with st.expander(
        " Add New Product",
        expanded=True
    ):
        product_category = st.selectbox(
            "Product Category",
            [
                "Book Sleeve",
                "Kindle Sleeve",
                "iPad Sleeve",
                "Laptop Sleeve",
                "Pen Strap Holder",
                "Other"
            ],
            key="new_product_category"
        )

        design = st.text_input(
            "Design / Variant Name",
            placeholder="Example: Pink Bunny",
            key="new_product_design"
        )

        sku = st.text_input(
            "SKU",
            placeholder="Example: BS-PINK-BUNNY",
            key="new_product_sku"
        )

        selling_price = st.number_input(
            "Selling Price (RM)",
            min_value=0.0,
            step=1.0,
            key="new_product_price"
        )

        packaging_cost = st.number_input(
            "Extra Packaging Cost per Unit (RM)",
            min_value=0.0,
            step=0.10,
            key="new_product_packaging"
        )

        platform_fee = st.number_input(
            "Platform Fee per Unit (RM)",
            min_value=0.0,
            step=0.10,
            key="new_product_platform_fee"
        )

        finished_stock = st.number_input(
            "Current Finished Stock",
            min_value=0,
            step=1,
            key="new_product_stock"
        )

        product_status = st.selectbox(
            "Product Status",
            ["Active", "Discontinued"],
            index=0,
            key="new_product_status",
            help="Discontinued products stay available for historical Shopee sales but are hidden from normal production."
        )

        product_image = st.file_uploader(
            "Product Image",
            type=[
                "png",
                "jpg",
                "jpeg",
                "webp"
            ],
            key="new_product_image"
        )

        if st.button(
            "Save Product",
            type="primary",
            key="save_product"
        ):
            if not design.strip():
                st.error(
                    "Please enter the design name."
                )

            else:
                image_path = None

                if product_image:
                    safe_name = (
                        product_image.name
                        .replace(" ", "_")
                    )

                    image_path = os.path.join(
                        "product_images",
                        safe_name
                    )

                    with open(
                        image_path,
                        "wb"
                    ) as f:
                        f.write(
                            product_image.getbuffer()
                        )

                add_product(
                    product_category,
                    design.strip(),
                    sku.strip(),
                    selling_price,
                    packaging_cost,
                    platform_fee,
                    finished_stock,
                    image_path,
                    product_status
                )

                st.rerun()

    # --------------------------------------------------------
    # PRODUCT LIST
    # --------------------------------------------------------

    st.divider()
    st.subheader("Saved Products")

    products = get_products()

    if not products:
        st.info("No products added yet.")

    else:
        product_categories = [
            "Book Sleeve",
            "Kindle Sleeve",
            "iPad Sleeve",
            "Laptop Sleeve",
            "Pen Strap Holder",
            "Other"
        ]

        for product in products:
            product_id = int(product["id"])
            edit_key = f"inline_edit_product_{product_id}"
            delete_key = f"inline_delete_confirm_{product_id}"

            with st.container(border=True):
                col_image, col_main, col_actions = st.columns([1, 5, 2])

                with col_image:
                    image_path = product["image_path"]

                    if image_path:
                        image_path = image_path.replace("\\", "/")
                        full_image_path = os.path.join(
                            os.path.dirname(os.path.abspath(__file__)),
                            image_path
                        )

                        if os.path.exists(full_image_path):
                            with open(full_image_path, "rb") as image_file:
                                image_bytes = image_file.read()
                            st.image(image_bytes, width=100)
                        else:
                            st.caption("Image file not found")
                    else:
                        st.caption("No image")

                with col_main:
                    st.markdown(f"### {product['design']}")
                    st.caption(product["category"])

                    status_value = (
                        product["status"]
                        if "status" in product.keys()
                        else "Active"
                    )
                    if status_value == "Discontinued":
                        st.caption(" Discontinued")
                    else:
                        st.caption(" Active")

                    if product["sku"]:
                        st.caption(f"SKU: {product['sku']}")

                    material_cost = calculate_product_material_cost(product_id)
                    total_cost = (
                        material_cost
                        + float(product["packaging_cost"] or 0)
                        + float(product["platform_fee"] or 0)
                    )
                    profit = float(product["selling_price"] or 0) - total_cost

                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("Stock", int(product["stock"] or 0))
                    c2.metric(
                        "Selling Price",
                        f"RM {float(product['selling_price'] or 0):.2f}"
                    )
                    c3.metric("Modal", f"RM {total_cost:.2f}")
                    c4.metric("Profit / Unit", f"RM {profit:.2f}")

                with col_actions:
                    if st.button(
                        " Edit",
                        key=f"edit_button_{product_id}",
                        use_container_width=True
                    ):
                        st.session_state[edit_key] = not st.session_state.get(
                            edit_key, False
                        )
                        st.session_state[delete_key] = False
                        st.rerun()

                    if st.button(
                        " Delete",
                        key=f"delete_button_{product_id}",
                        use_container_width=True
                    ):
                        st.session_state[delete_key] = True
                        st.session_state[edit_key] = False
                        st.rerun()

                with st.expander(
                    f" View Modal Breakdown — RM {total_cost:.2f}",
                    expanded=False
                ):
                    show_modal_breakdown(product)

                if st.session_state.get(edit_key, False):
                    st.markdown("#### Edit Product")

                    category_index = (
                        product_categories.index(product["category"])
                        if product["category"] in product_categories
                        else 0
                    )

                    edit_category = st.selectbox(
                        "Product Category",
                        product_categories,
                        index=category_index,
                        key=f"inline_category_{product_id}"
                    )
                    edit_design = st.text_input(
                        "Design / Product Name",
                        value=product["design"],
                        key=f"inline_design_{product_id}"
                    )
                    edit_sku = st.text_input(
                        "SKU",
                        value=product["sku"] or "",
                        key=f"inline_sku_{product_id}"
                    )

                    ec1, ec2 = st.columns(2)
                    with ec1:
                        edit_price = st.number_input(
                            "Selling Price (RM)",
                            min_value=0.0,
                            value=float(product["selling_price"] or 0),
                            key=f"inline_price_{product_id}"
                        )
                        edit_packaging = st.number_input(
                            "Extra Packaging Cost (RM)",
                            min_value=0.0,
                            value=float(product["packaging_cost"] or 0),
                            key=f"inline_packaging_{product_id}"
                        )

                    with ec2:
                        edit_platform_fee = st.number_input(
                            "Platform Fee per Unit (RM)",
                            min_value=0.0,
                            value=float(product["platform_fee"] or 0),
                            key=f"inline_fee_{product_id}"
                        )
                        edit_stock = st.number_input(
                            "Finished Stock",
                            min_value=0,
                            value=int(product["stock"] or 0),
                            step=1,
                            key=f"inline_stock_{product_id}"
                        )

                    current_status = (
                        product["status"]
                        if "status" in product.keys()
                        else "Active"
                    )
                    edit_status = st.selectbox(
                        "Product Status",
                        ["Active", "Discontinued"],
                        index=0 if current_status == "Active" else 1,
                        key=f"inline_status_{product_id}"
                    )

                    b1, b2 = st.columns(2)
                    with b1:
                        if st.button(
                            " Save Changes",
                            type="primary",
                            key=f"inline_save_{product_id}",
                            use_container_width=True
                        ):
                            update_product(
                                product_id,
                                edit_category,
                                edit_design,
                                edit_sku,
                                edit_price,
                                edit_packaging,
                                edit_platform_fee,
                                edit_stock,
                                edit_status
                            )
                            st.session_state[edit_key] = False
                            st.rerun()

                    with b2:
                        if st.button(
                            "Cancel",
                            key=f"inline_cancel_{product_id}",
                            use_container_width=True
                        ):
                            st.session_state[edit_key] = False
                            st.rerun()

                if st.session_state.get(delete_key, False):
                    st.warning(
                        f"Delete **{product['design']}**? "
                        "Its product recipe will also be removed. "
                        "This cannot be undone."
                    )
                    d1, d2 = st.columns(2)

                    with d1:
                        if st.button(
                            "Yes, Delete Product",
                            type="primary",
                            key=f"inline_confirm_delete_{product_id}",
                            use_container_width=True
                        ):
                            delete_product(product_id)
                            st.session_state.pop(delete_key, None)
                            st.session_state.pop(edit_key, None)
                            st.rerun()

                    with d2:
                        if st.button(
                            "Cancel",
                            key=f"inline_cancel_delete_{product_id}",
                            use_container_width=True
                        ):
                            st.session_state[delete_key] = False
                            st.rerun()


# ============================================================
# PRODUCT RECIPE
# ============================================================

with recipe_tab:
    st.subheader("Product Recipe")

    st.write(
        "Define the materials needed to produce "
        "ONE unit of each product."
    )

    products = get_products()
    materials = get_materials()

    if not products:
        st.warning(
            "Add at least one product first."
        )

    elif not materials:
        st.warning(
            "Add materials first."
        )

    else:
        product_options = {
            f"{p['category']} — {p['design']}": p
            for p in products
        }

        selected_product_name = st.selectbox(
            "Choose Product",
            list(product_options.keys()),
            key="recipe_product"
        )

        selected_product = product_options[
            selected_product_name
        ]

        recipes = get_product_materials(
            selected_product["id"]
        )

        st.divider()
        st.markdown("### Add Material to Recipe")

        material_options = {
            f"{m['name']} — {m['category']}": m
            for m in materials
        }

        selected_material_name = st.selectbox(
            "Material",
            list(material_options.keys()),
            key="recipe_material"
        )

        selected_material = material_options[
            selected_material_name
        ]

        method = method_for_category(
            selected_material["category"]
        )

        quantity_used = 0
        pieces_count = 0
        piece_width = 0
        piece_height = 0
        wastage = 0
        yield_per_metre = 0.0
        estimated_cost = 0

        # ----------------------------------------------------
        # FABRIC / SHEET MATERIAL
        # ----------------------------------------------------

        if method == "area":
            st.info(
                "Fabric-like materials are costed using your REAL cutting yield. "
                "Piece dimensions are kept only as a production reference."
            )

            pieces_count = st.number_input(
                "Number of Pieces",
                min_value=1,
                value=2,
                step=1,
                key="recipe_pieces"
            )

            piece_width = st.number_input(
                "Width of Each Piece (cm)",
                min_value=0.0,
                value=25.0,
                step=0.5,
                key="recipe_piece_width"
            )

            piece_height = st.number_input(
                "Height of Each Piece (cm)",
                min_value=0.0,
                value=23.0,
                step=0.5,
                key="recipe_piece_height"
            )

            yield_per_metre = st.number_input(
                f"How many {selected_product['category']} can you actually make from 1 metre?",
                min_value=0.0,
                value=7.0,
                step=1.0,
                key="recipe_yield_per_metre",
                help=(
                    "Use your real cutting result. Example: if 1 metre gives "
                    "7 Book Sleeves, enter 7. Reusable scraps for smaller products "
                    "do not change this Book Sleeve yield."
                )
            )

            unit_price = float(
                selected_material["unit_price"]
                if "unit_price" in selected_material.keys()
                and selected_material["unit_price"] is not None
                else selected_material["average_unit_cost"] or 0
            )

            if yield_per_metre > 0:
                estimated_cost = unit_price / yield_per_metre
                st.success(
                    f"RM {unit_price:.2f}/m ÷ {yield_per_metre:g} "
                    f"= RM {estimated_cost:.2f} per {selected_product['category']}"
                )
            else:
                st.warning("Enter the real number of products you get from 1 metre.")

            st.caption(
                "The dimensions above are reference information only. "
                "Neomii no longer uses cm² or a wastage percentage to calculate this material cost."
            )

        # ----------------------------------------------------
        # MATERIAL USED BY LENGTH
        # ----------------------------------------------------

        elif method == "length":
            st.info(
                "Enter how much length is used for "
                "ONE product."
            )

            centimetres_used = st.number_input(
                "Length Used per Product (cm)",
                min_value=0.0,
                step=1.0,
                value=10.0,
                key="recipe_length_cm"
            )

            quantity_used = (
                centimetres_used / 100
            )

            unit_price = float(
                selected_material["unit_price"]
                if "unit_price" in selected_material.keys()
                and selected_material["unit_price"] is not None
                else selected_material["average_unit_cost"] or 0
            )

            estimated_cost = (
                unit_price
                * quantity_used
            )

            st.success(
                f"{centimetres_used:.0f} cm used"
                f" | Estimated cost: "
                f"RM {estimated_cost:.2f}"
            )

        # ----------------------------------------------------
        # MATERIAL USED BY PIECE
        # ----------------------------------------------------

        else:
            st.info(
                "Enter the number of units used for "
                "ONE product."
            )

            quantity_used = st.number_input(
                f"Quantity Used "
                f"({selected_material['unit']})",
                min_value=0.0,
                value=1.0,
                step=1.0,
                key="recipe_unit_qty"
            )

            unit_price = float(
                selected_material["unit_price"]
                if "unit_price" in selected_material.keys()
                and selected_material["unit_price"] is not None
                else selected_material["average_unit_cost"] or 0
            )

            estimated_cost = (
                unit_price
                * quantity_used
            )

            st.success(
                f"Estimated cost: "
                f"RM {estimated_cost:.2f}"
            )

        existing_material_ids = [
            recipe["material_id"]
            for recipe in recipes
        ]

        if (
            selected_material["id"]
            in existing_material_ids
        ):
            st.warning(
                "This material is already in this recipe. "
                "Remove the old recipe line before adding "
                "it again."
            )

        else:
            if st.button(
                "Add to Product Recipe",
                type="primary",
                key="add_recipe"
            ):
                add_product_material(
                    selected_product["id"],
                    selected_material["id"],
                    quantity_used,
                    pieces_count,
                    piece_width,
                    piece_height,
                    wastage,
                    yield_per_metre
                )

                st.rerun()

        # ----------------------------------------------------
        # CURRENT RECIPE
        # ----------------------------------------------------

        st.divider()

        st.markdown(
            f"### Recipe: "
            f"{selected_product['design']}"
        )

        recipes = get_product_materials(
            selected_product["id"]
        )

        if not recipes:
            st.info(
                "No materials added yet."
            )

        else:
            total_material_cost = 0

            for recipe in recipes:
                item_cost = (
                    calculate_recipe_item_cost(
                        recipe
                    )
                )

                total_material_cost += (
                    item_cost
                )

                recipe_method = (
                    method_for_category(
                        recipe[
                            "material_category"
                        ]
                    )
                )

                with st.container(border=True):
                    col1, col2, col3 = st.columns(
                        [5, 2, 1]
                    )

                    with col1:
                        st.write(
                            f"**{recipe['material_name']}**"
                        )

                        st.caption(
                            recipe[
                                "material_category"
                            ]
                        )

                        if recipe_method == "area":
                            if (
                                float(
                                    recipe[
                                        "piece_width_cm"
                                    ] or 0
                                ) == 0
                                or float(
                                    recipe[
                                        "piece_height_cm"
                                    ] or 0
                                ) == 0
                            ):
                                st.warning(
                                    "This old recipe entry "
                                    "does not contain piece "
                                    "dimensions. Remove it and "
                                    "add the material again."
                                )

                            else:
                                st.write(
                                    f"{recipe['pieces_count']} pieces × "
                                    f"{recipe['piece_width_cm']:.1f} × "
                                    f"{recipe['piece_height_cm']:.1f} cm"
                                )

                                current_yield = float(
                                    recipe["yield_per_metre"]
                                    if "yield_per_metre" in recipe.keys()
                                    and recipe["yield_per_metre"] is not None
                                    else 0
                                )

                                if current_yield > 0:
                                    st.caption(
                                        f"Real cutting yield: {current_yield:g} "
                                        f"{selected_product['category']}(s) per metre"
                                    )
                                else:
                                    st.warning(
                                        "Real cutting yield has not been set for this old recipe line."
                                    )

                                new_yield = st.number_input(
                                    "Real yield per metre",
                                    min_value=0.0,
                                    value=current_yield,
                                    step=1.0,
                                    key=f"edit_recipe_yield_{recipe['id']}"
                                )

                                if st.button(
                                    "Save Yield",
                                    key=f"save_recipe_yield_{recipe['id']}"
                                ):
                                    if new_yield <= 0:
                                        st.error("Yield must be more than zero.")
                                    else:
                                        update_product_material_yield(
                                            recipe["id"],
                                            new_yield
                                        )
                                        st.rerun()

                        elif recipe_method == "length":
                            st.write(
                                f"{float(recipe['quantity_used'] or 0) * 100:.0f} cm"
                            )

                        else:
                            st.write(
                                f"{float(recipe['quantity_used'] or 0):g} "
                                f"{recipe['unit']}"
                            )

                    with col2:
                        st.write(
                            f"**RM {item_cost:.2f}**"
                        )

                    with col3:
                        if st.button(
                            "Remove",
                            key=f"remove_recipe_{recipe['id']}"
                        ):
                            delete_product_material(
                                recipe["id"]
                            )

                            st.rerun()

            st.success(
                f"Total material cost per "
                f"{selected_product['design']}: "
                f"RM {total_material_cost:.2f}"
            )

            total_modal = (
                total_material_cost
                + float(
                    selected_product[
                        "packaging_cost"
                    ] or 0
                )
                + float(
                    selected_product[
                        "platform_fee"
                    ] or 0
                )
            )

            expected_profit = (
                float(
                    selected_product[
                        "selling_price"
                    ] or 0
                )
                - total_modal
            )

            col1, col2, col3 = st.columns(3)

            col1.metric(
                "Materials",
                f"RM {total_material_cost:.2f}"
            )

            col2.metric(
                "Total Modal",
                f"RM {total_modal:.2f}"
            )

            col3.metric(
                "Profit / Unit",
                f"RM {expected_profit:.2f}"
            )


# ============================================================
# PRODUCTION
# ============================================================

with production_tab:
    show_production_page()


# ============================================================
# SALES
# ============================================================

with sales_tab:
    show_sales_page()


# ============================================================
# SETTINGS
# ============================================================

with settings_tab:
    st.subheader("Shop Settings")

    current_settings = get_shop_settings()

    current_name = "Neomii"
    current_logo = None

    if current_settings:
        current_name = (
            current_settings["shop_name"]
        )

        current_logo = (
            current_settings["logo_path"]
        )

    new_shop_name = st.text_input(
        "Shop Name",
        value=current_name
    )

    current_logo_full_path = None
    if current_logo:
        current_logo_full_path = (
            current_logo
            if os.path.isabs(current_logo)
            else os.path.join(APP_DIR, current_logo)
        )

    if (
        current_logo_full_path
        and os.path.exists(current_logo_full_path)
    ):
        st.write("Current Logo")

        st.image(
            current_logo_full_path,
            width=120
        )

        change_logo = st.checkbox(
            "Change logo"
        )

    else:
        change_logo = True

    new_logo = None

    if change_logo:
        new_logo = st.file_uploader(
            "Upload Shop Logo",
            type=[
                "png",
                "jpg",
                "jpeg",
                "webp"
            ]
        )

    if st.button(
        "Save Settings",
        type="primary"
    ):
        logo_to_save = current_logo

        if new_logo:
            safe_logo_name = (
                new_logo.name.replace(
                    " ",
                    "_"
                )
            )

            logo_to_save = os.path.join(
                "assets",
                safe_logo_name
            )

            logo_write_path = os.path.join(
                APP_DIR,
                logo_to_save
            )

            with open(
                logo_write_path,
                "wb"
            ) as f:
                f.write(
                    new_logo.getbuffer()
                )

        update_shop_settings(
            new_shop_name,
            logo_to_save
        )

        st.rerun()