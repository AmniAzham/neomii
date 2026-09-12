import os
import pandas as pd
import streamlit as st

from database import (
    get_products,
    get_product_materials,
    record_sale,
    get_sales_history,
)


CUT_CATEGORIES = {
    "Outer Fabric", "Lining Fabric", "Fabric", "Batting", "Interfacing"
}
LENGTH_CATEGORIES = {"Elastic", "Velcro", "Ribbon"}


def method_for_category(category):
    if category in CUT_CATEGORIES:
        return "area"
    if category in LENGTH_CATEGORIES:
        return "length"
    return "count"


def calculate_product_material_cost(product_id):
    recipes = get_product_materials(product_id)
    total = 0.0

    for recipe in recipes:
        method = method_for_category(recipe["material_category"])
        unit_price = float(
            recipe["unit_price"]
            if "unit_price" in recipe.keys() and recipe["unit_price"] is not None
            else recipe["average_unit_cost"] or 0
        )

        if method == "area":
            yield_per_metre = float(recipe["yield_per_metre"] or 0)
            if yield_per_metre > 0:
                total += unit_price / yield_per_metre
        else:
            total += unit_price * float(recipe["quantity_used"] or 0)

    return total


def show_sales_page():
    st.subheader("Sales")

    st.write(
        "Record a sale and Neomii will deduct the finished-product stock "
        "automatically. You can also record an older sale without deducting stock."
    )

    if "sales_success" in st.session_state:
        st.success(st.session_state.pop("sales_success"))

    products = get_products()

    if not products:
        st.info("Add a product before recording sales.")
        return

    product_options = {
        f"{p['category']} — {p['design']}": p
        for p in products
    }

    selected_label = st.selectbox(
        "Product / Design",
        list(product_options.keys()),
        key="sales_product"
    )
    product = product_options[selected_label]

    left, right = st.columns([1, 3])

    with left:
        if product["image_path"] and os.path.exists(product["image_path"]):
            st.image(product["image_path"], use_container_width=True)
        else:
            st.markdown("### 🧵")

    with right:
        st.markdown(f"### {product['design']}")
        st.caption(product["category"])
        if product["sku"]:
            st.caption(f"SKU: {product['sku']}")
        st.metric("Finished Stock Available", int(product["stock"] or 0))

    quantity = st.number_input(
        "Quantity Sold",
        min_value=1,
        value=1,
        step=1,
        key=f"sales_qty_{product['id']}"
    )

    normal_price = float(product["selling_price"] or 0)
    sale_price = st.number_input(
        "Actual Selling Price per Unit (RM)",
        min_value=0.0,
        value=normal_price,
        step=1.0,
        key=f"sales_price_{product['id']}",
        help="Change this if you sold the item at a discount or different price."
    )

    historical = st.checkbox(
        "Historical sale — do not deduct finished stock",
        value=False,
        key=f"historical_sale_{product['id']}",
        help=(
            "Use this only for a sale that you already deducted manually "
            "from your inventory."
        )
    )

    material_cost = calculate_product_material_cost(product["id"])
    modal_per_unit = (
        material_cost
        + float(product["packaging_cost"] or 0)
        + float(product["platform_fee"] or 0)
    )

    revenue = float(sale_price) * int(quantity)
    total_modal = modal_per_unit * int(quantity)
    profit = revenue - total_modal

    st.divider()
    st.markdown("### Sale Preview")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Revenue", f"RM {revenue:.2f}")
    c2.metric("Modal", f"RM {total_modal:.2f}")
    c3.metric("Est. Profit", f"RM {profit:.2f}")
    c4.metric(
        "Stock After",
        int(product["stock"] or 0)
        if historical
        else max(int(product["stock"] or 0) - int(quantity), 0)
    )

    if historical:
        st.info(
            "Historical mode is ON. This sale will be added to Sales History, "
            "but finished stock will NOT change."
        )
    elif int(product["stock"] or 0) < int(quantity):
        st.error(
            "Not enough finished stock for this sale. "
            "Record production or correct the stock first."
        )

    can_record = (
        sale_price >= 0
        and (
            historical
            or int(product["stock"] or 0) >= int(quantity)
        )
    )

    if st.button(
        "Record Sale",
        type="primary",
        disabled=not can_record,
        key=f"record_sale_{product['id']}"
    ):
        success, result = record_sale(
            product["id"],
            int(quantity),
            float(sale_price),
            modal_per_unit,
            deduct_stock=not historical
        )

        if success:
            if historical:
                message = (
                    f"Historical sale recorded: {int(quantity)} × "
                    f"{product['design']}. Finished stock was not changed."
                )
            else:
                message = (
                    f"Sale recorded: {int(quantity)} × {product['design']}. "
                    f"Finished stock has been deducted."
                )

            st.session_state.sales_success = message
            st.rerun()
        else:
            st.error(f"Sale was not recorded: {result}")

    st.divider()
    st.markdown("### Sales History")

    history = get_sales_history(limit=100)

    if not history:
        st.info("No sales recorded yet.")
        return

    rows = []
    total_revenue = 0.0
    total_profit = 0.0
    total_units = 0

    for sale in history:
        total_revenue += float(sale["revenue"] or 0)
        total_profit += float(sale["estimated_profit"] or 0)
        total_units += int(sale["quantity_sold"] or 0)

        rows.append({
            "Date": sale["sold_at"],
            "Product": sale["design"],
            "Qty": sale["quantity_sold"],
            "Price / Unit": f"RM {float(sale['selling_price_per_unit']):.2f}",
            "Revenue": f"RM {float(sale['revenue']):.2f}",
            "Modal": f"RM {float(sale['total_modal']):.2f}",
            "Est. Profit": f"RM {float(sale['estimated_profit']):.2f}",
            "Stock Deducted": "Yes" if sale["deduct_stock"] else "No",
        })

    h1, h2, h3 = st.columns(3)
    h1.metric("Units in History", total_units)
    h2.metric("Revenue in History", f"RM {total_revenue:.2f}")
    h3.metric("Est. Profit in History", f"RM {total_profit:.2f}")

    st.dataframe(
        pd.DataFrame(rows),
        use_container_width=True,
        hide_index=True
    )
