import os
import pandas as pd
import streamlit as st

from database import (
    get_products,
    get_product_materials,
    record_production,
    get_production_history,
    get_production_material_usage,
)


CUT_CATEGORIES = {
    "Outer Fabric",
    "Lining Fabric",
    "Fabric",
    "Batting",
    "Interfacing",
}

LENGTH_CATEGORIES = {
    "Elastic",
    "Velcro",
    "Ribbon",
}


def method_for_category(category):
    if category in CUT_CATEGORIES:
        return "area"
    if category in LENGTH_CATEGORIES:
        return "length"
    return "count"


def _format_qty(value, unit):
    value = float(value)

    if unit == "m":
        return f"{value:.3f} m"

    if abs(value - round(value)) < 1e-9:
        return f"{int(round(value))} {unit}"

    return f"{value:.3f} {unit}"


def calculate_material_requirements(recipes, quantity_produced):
    aggregated = {}
    errors = []

    for recipe in recipes:
        category = recipe["material_category"]
        method = method_for_category(category)
        material_id = int(recipe["material_id"])
        material_name = recipe["material_name"]

        if method == "area":
            yield_per_metre = float(recipe["yield_per_metre"] or 0)

            if yield_per_metre <= 0:
                errors.append(
                    f"{material_name}: real yield per metre has not been set."
                )
                continue

            required = float(quantity_produced) / yield_per_metre
            unit = "m"
            formula = (
                f"{quantity_produced} ÷ {yield_per_metre:g} "
                f"= {required:.3f} m"
            )

        elif method == "length":
            per_product = float(recipe["quantity_used"] or 0)
            required = per_product * float(quantity_produced)
            unit = "m"
            formula = (
                f"{per_product * 100:g} cm × {quantity_produced} "
                f"= {required * 100:g} cm"
            )

        else:
            per_product = float(recipe["quantity_used"] or 0)
            required = per_product * float(quantity_produced)
            unit = recipe["unit"] or "piece"
            formula = (
                f"{per_product:g} {unit} × {quantity_produced} "
                f"= {required:g} {unit}"
            )

        available = float(recipe["current_quantity"] or 0)

        if material_id not in aggregated:
            aggregated[material_id] = {
                "material_id": material_id,
                "material_name": material_name,
                "category": category,
                "required": 0.0,
                "available": available,
                "unit": unit,
                "formulas": [],
            }

        aggregated[material_id]["required"] += required
        aggregated[material_id]["formulas"].append(formula)

    requirements = list(aggregated.values())

    for item in requirements:
        item["after"] = item["available"] - item["required"]
        item["enough"] = item["after"] >= -1e-9
        item["formula"] = " + ".join(item["formulas"])

    return requirements, errors


def show_production_page():
    st.subheader("Production")

    st.write(
        "Record products you have actually made. Neomii will increase "
        "finished-product stock and automatically deduct the recipe materials."
    )

    if "production_success" in st.session_state:
        st.success(st.session_state.pop("production_success"))

    products = [
        p for p in get_products()
        if (p["status"] if "status" in p.keys() else "Active") == "Active"
    ]

    if not products:
        st.info("Add a product before recording production.")
        return

    product_options = {
        f"{p['category']} — {p['design']}": p
        for p in products
    }

    selected_label = st.selectbox(
        "Product / Design",
        list(product_options.keys()),
        key="production_product"
    )

    product = product_options[selected_label]

    top_left, top_right = st.columns([1, 3])

    with top_left:
        if (
            product["image_path"]
            and os.path.exists(product["image_path"])
        ):
            st.image(product["image_path"], use_container_width=True)
        else:
            st.markdown("### ")

    with top_right:
        st.markdown(f"### {product['design']}")
        st.caption(product["category"])

        if product["sku"]:
            st.caption(f"SKU: {product['sku']}")

        st.metric(
            "Current Finished Stock",
            int(product["stock"] or 0)
        )

    quantity_produced = st.number_input(
        "Quantity Made",
        min_value=1,
        value=1,
        step=1,
        key=f"production_qty_{product['id']}"
    )

    recipes = get_product_materials(product["id"])

    st.divider()
    st.markdown("### Material Deduction Preview")

    if not recipes:
        st.warning(
            "This product does not have a recipe yet. "
            "Add its materials under Product Recipe first."
        )
        return

    requirements, recipe_errors = calculate_material_requirements(
        recipes,
        int(quantity_produced)
    )

    if recipe_errors:
        for error in recipe_errors:
            st.error(error)

    rows = []

    for item in requirements:
        rows.append({
            "Material": item["material_name"],
            "Calculation": item["formula"],
            "Required": _format_qty(item["required"], item["unit"]),
            "Available": _format_qty(item["available"], item["unit"]),
            "After Production": (
                _format_qty(max(item["after"], 0), item["unit"])
                if item["enough"]
                else f"SHORT by {_format_qty(abs(item['after']), item['unit'])}"
            ),
            "Status": " Enough" if item["enough"] else " Not enough",
        })

    if rows:
        st.dataframe(
            pd.DataFrame(rows),
            use_container_width=True,
            hide_index=True
        )

    insufficient = [
        item for item in requirements
        if not item["enough"]
    ]

    current_finished = int(product["stock"] or 0)
    new_finished = current_finished + int(quantity_produced)

    c1, c2, c3 = st.columns(3)
    c1.metric("Current Finished Stock", current_finished)
    c2.metric("Making Now", int(quantity_produced))
    c3.metric("Finished Stock After", new_finished)

    deductions = [
        {
            "material_id": item["material_id"],
            "quantity_used": item["required"],
            "unit": item["unit"],
        }
        for item in requirements
    ]

    can_produce = (
        bool(requirements)
        and not recipe_errors
        and not insufficient
    )

    if insufficient:
        st.error(
            "Production cannot be recorded because one or more "
            "materials do not have enough stock."
        )

    st.caption(
        "For fabric-like materials, inventory is deducted using the "
        "real yield saved in the recipe. Example: 5 products from a "
        "7-per-metre yield deducts 5 ÷ 7 = 0.714 m."
    )

    if st.button(
        f" Record Production of {int(quantity_produced)}",
        type="primary",
        disabled=not can_produce,
        key=f"record_production_{product['id']}"
    ):
        success, result = record_production(
            product["id"],
            int(quantity_produced),
            deductions
        )

        if success:
            st.session_state.production_success = (
                f"Production recorded: {int(quantity_produced)} × "
                f"{product['design']}. Finished stock and material "
                f"inventory have been updated."
            )
            st.rerun()
        else:
            st.error(f"Production was not recorded: {result}")

    st.divider()
    st.markdown("### Production History")

    history = get_production_history(limit=30)

    if not history:
        st.info("No production has been recorded yet.")
        return

    history_rows = []

    for batch in history:
        history_rows.append({
            "Date": batch["produced_at"],
            "Product": batch["design"],
            "Category": batch["category"],
            "Quantity Made": batch["quantity_produced"],
        })

    st.dataframe(
        pd.DataFrame(history_rows),
        use_container_width=True,
        hide_index=True
    )

    with st.expander("View material usage for a production batch"):
        history_options = {
            (
                f"#{batch['id']} — {batch['produced_at']} — "
                f"{batch['design']} × {batch['quantity_produced']}"
            ): batch
            for batch in history
        }

        selected_history_label = st.selectbox(
            "Production Batch",
            list(history_options.keys()),
            key="production_history_batch"
        )

        selected_batch = history_options[selected_history_label]
        usage = get_production_material_usage(selected_batch["id"])

        usage_rows = []

        for item in usage:
            unit = item["unit"] or ""
            usage_rows.append({
                "Material": item["material_name"],
                "Used": _format_qty(item["quantity_used"], unit),
            })

        if usage_rows:
            st.dataframe(
                pd.DataFrame(usage_rows),
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info("No material usage was recorded for this batch.")
