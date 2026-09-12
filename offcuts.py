import pandas as pd
import streamlit as st

from database import (
    get_products,
    get_product_materials,
    get_material_category_offcut_rules,
    add_material_category_offcut_rule,
    delete_material_category_offcut_rule,
    ensure_material_category_offcuts,
)

FABRIC_LIKE = {
    "Outer Fabric",
    "Lining Fabric",
    "Fabric",
    "Batting",
    "Interfacing",
}


def show_offcuts_page():
    # Make sure reusable-offcut inventory items exist for any rules
    # that were saved before this update.
    ensure_material_category_offcuts()
    st.subheader("Reusable Offcuts ♻️")

    st.write(
        "Create one offcut rule by material category. "
        "Neomii will apply it automatically to every matching material "
        "used by that product category."
    )

    products = get_products()
    active = [
        p for p in products
        if (p["status"] if "status" in p.keys() else "Active") == "Active"
    ]

    product_categories = sorted({p["category"] for p in active})
    if not product_categories:
        st.warning("Add an active product first.")
        return

    product_category = st.selectbox(
        "Source Product Category",
        product_categories,
        key="offcut_source_product_category"
    )

    # Find material categories actually used by this product category.
    material_categories = set()
    for product in active:
        if product["category"] != product_category:
            continue
        for recipe in get_product_materials(product["id"]):
            if recipe["material_category"] in FABRIC_LIKE:
                material_categories.add(recipe["material_category"])

    material_categories = sorted(material_categories)

    if not material_categories:
        st.warning(
            f"No fabric-like recipe material categories were found in "
            f"{product_category}."
        )
        return

    source_material_category = st.selectbox(
        "Source Material Category",
        material_categories,
        key="offcut_source_material_category",
        help=(
            "Choose Outer Fabric, Lining Fabric, Batting, etc. "
            "The rule will apply to every material in that category."
        )
    )

    sets_per_metre = st.number_input(
        "Usable Kindle Sets Created per 1 Metre",
        min_value=0.0,
        value=2.0,
        step=0.5,
        key="material_category_offcuts_per_metre"
    )

    suffix = st.text_input(
        "Offcut Name Suffix",
        value="Kindle usable offcut",
        key="offcut_suffix",
        help=(
            "Neomii keeps each material separate automatically. "
            "Example: Pink Bunny Fabric → Pink Bunny Fabric — Kindle usable offcut."
        )
    )

    st.info(
        f"This one rule will apply to **all {product_category} designs** and "
        f"every material whose category is **{source_material_category}**."
    )

    st.caption(
        "Example: if each 1 m of Book Sleeve outer fabric leaves enough "
        "usable fabric for 2 Kindle Sleeves, enter 2. "
        "Each fabric/design keeps its own offcut stock."
    )

    if st.button("Save Material-Category Rule", type="primary"):
        if sets_per_metre <= 0:
            st.error("Usable sets per metre must be above zero.")
        elif not suffix.strip():
            st.error("Enter an offcut name suffix.")
        else:
            ok, err = add_material_category_offcut_rule(
                product_category,
                source_material_category,
                sets_per_metre,
                suffix.strip()
            )
            if ok:
                st.success(
                    f"Saved: {product_category} + {source_material_category}. "
                    "You do not need to make a rule for each individual material."
                )
                st.rerun()
            else:
                st.error(err)

    st.divider()
    st.markdown("### Saved Material-Category Rules")

    rules = get_material_category_offcut_rules()

    if not rules:
        st.info("No material-category offcut rules yet.")
        return

    rows = []
    for r in rules:
        rows.append({
            "Product Category": r["source_product_category"],
            "Material Category": r["source_material_category"],
            "Creates per 1 m": f"{float(r['offcuts_per_metre']):.2f} sets",
            "Naming": f"<material> — {r['offcut_name_suffix']}",
        })

    st.dataframe(
        pd.DataFrame(rows),
        use_container_width=True,
        hide_index=True
    )

    with st.expander("Delete a rule"):
        options = {
            (
                f"{r['source_product_category']} | "
                f"{r['source_material_category']}"
            ): r
            for r in rules
        }

        selected = st.selectbox(
            "Rule",
            list(options.keys()),
            key="delete_material_category_rule"
        )

        if st.button("Delete Material-Category Rule"):
            delete_material_category_offcut_rule(options[selected]["id"])
            st.rerun()

    st.divider()
    st.markdown("### How this works")

    st.write(
        "If you save **Book Sleeve + Outer Fabric = 2 sets/m**, then:"
    )
    st.code(
        "Pink Bunny Fabric used 1.0 m  →  "
        "Pink Bunny Fabric — Kindle usable offcut +2\n"
        "Forest Fabric used 0.5 m      →  "
        "Forest Fabric — Kindle usable offcut +1"
    )

    st.write(
        "So you only create the rule once, but Neomii still keeps "
        "the different fabric designs separate."
    )
