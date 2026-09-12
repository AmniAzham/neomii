import sqlite3

DB_NAME = "neomii.db"


def get_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def initialize_database():
    conn = get_connection()
    cursor = conn.cursor()

    # -------------------------------------------------
    # PRODUCTS
    # -------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            design TEXT NOT NULL,
            sku TEXT,
            selling_price REAL DEFAULT 0,
            material_cost REAL DEFAULT 0,
            packaging_cost REAL DEFAULT 0,
            platform_fee REAL DEFAULT 0,
            stock INTEGER DEFAULT 0,
            image_path TEXT
        )
    """)


    # Product status migration
    cursor.execute("PRAGMA table_info(products)")
    product_columns = [row["name"] for row in cursor.fetchall()]

    if "status" not in product_columns:
        cursor.execute("""
            ALTER TABLE products
            ADD COLUMN status TEXT DEFAULT 'Active'
        """)

    cursor.execute("""
        UPDATE products
        SET status = 'Active'
        WHERE status IS NULL OR TRIM(status) = ''
    """)

    # -------------------------------------------------
    # MATERIALS
    # -------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS materials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            purchase_price REAL DEFAULT 0,
            purchase_quantity REAL DEFAULT 0,
            unit TEXT,
            fabric_width_cm REAL DEFAULT 0,
            current_quantity REAL DEFAULT 0,
            measurement_method TEXT DEFAULT 'Unit',
            average_unit_cost REAL DEFAULT 0,
            unit_price REAL DEFAULT 0
        )
    """)

    # Migration for older databases
    cursor.execute("PRAGMA table_info(materials)")
    material_columns = [row["name"] for row in cursor.fetchall()]

    if "measurement_method" not in material_columns:
        cursor.execute("""
            ALTER TABLE materials
            ADD COLUMN measurement_method TEXT DEFAULT 'Unit'
        """)

    if "average_unit_cost" not in material_columns:
        cursor.execute("""
            ALTER TABLE materials
            ADD COLUMN average_unit_cost REAL DEFAULT 0
        """)

    if "unit_price" not in material_columns:
        cursor.execute("""
            ALTER TABLE materials
            ADD COLUMN unit_price REAL DEFAULT 0
        """)

    # Keep one simple legacy type: Measured or Unit.
    # The app itself derives the correct calculation from the material category.
    cursor.execute("""
        UPDATE materials
        SET measurement_method = 'Measured'
        WHERE category IN (
            'Fabric',
            'Outer Fabric',
            'Lining Fabric',
            'Batting',
            'Interfacing'
        )
    """)

    cursor.execute("""
        UPDATE materials
        SET measurement_method = 'Measured'
        WHERE category IN (
            'Elastic',
            'Velcro',
            'Ribbon'
        )
    """)

    cursor.execute("""
        UPDATE materials
        SET measurement_method = 'Unit'
        WHERE category NOT IN (
            'Fabric',
            'Outer Fabric',
            'Lining Fabric',
            'Batting',
            'Interfacing',
            'Elastic',
            'Velcro',
            'Ribbon'
        )
    """)

    # Calculate initial average cost for old records
    cursor.execute("""
        UPDATE materials
        SET average_unit_cost =
            CASE
                WHEN purchase_quantity > 0
                THEN purchase_price / purchase_quantity
                ELSE 0
            END
        WHERE average_unit_cost IS NULL
           OR average_unit_cost = 0
    """)

    # New costing model:
    # unit_price is the seller's price-list value (RM/metre or RM/piece).
    cursor.execute("""
        UPDATE materials
        SET unit_price =
            CASE
                WHEN average_unit_cost > 0 THEN average_unit_cost
                WHEN purchase_quantity > 0 THEN purchase_price / purchase_quantity
                ELSE 0
            END
        WHERE unit_price IS NULL OR unit_price = 0
    """)

    # -------------------------------------------------
    # PRODUCT RECIPES
    # -------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS product_materials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            material_id INTEGER NOT NULL,
            quantity_used REAL DEFAULT 0,
            pieces_count INTEGER DEFAULT 0,
            piece_width_cm REAL DEFAULT 0,
            piece_height_cm REAL DEFAULT 0,
            wastage_pct REAL DEFAULT 0,
            yield_per_metre REAL DEFAULT 0,
            FOREIGN KEY (product_id) REFERENCES products(id),
            FOREIGN KEY (material_id) REFERENCES materials(id)
        )
    """)

    # Migration for existing recipe rows
    cursor.execute("PRAGMA table_info(product_materials)")
    recipe_columns = [row["name"] for row in cursor.fetchall()]

    if "yield_per_metre" not in recipe_columns:
        cursor.execute("""
            ALTER TABLE product_materials
            ADD COLUMN yield_per_metre REAL DEFAULT 0
        """)

    # -------------------------------------------------
    # MATERIAL PURCHASE / RESTOCK HISTORY
    # -------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS material_restock_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            material_id INTEGER NOT NULL,
            quantity_added REAL NOT NULL,
            total_cost REAL NOT NULL,
            unit_cost REAL NOT NULL,
            purchased_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (material_id) REFERENCES materials(id)
        )
    """)


    # -------------------------------------------------
    # PRODUCTION HISTORY
    # -------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS production_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            quantity_produced INTEGER NOT NULL,
            produced_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES products(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS production_material_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            production_id INTEGER NOT NULL,
            material_id INTEGER NOT NULL,
            quantity_used REAL NOT NULL,
            unit TEXT,
            FOREIGN KEY (production_id) REFERENCES production_history(id),
            FOREIGN KEY (material_id) REFERENCES materials(id)
        )
    """)


    # -------------------------------------------------
    # SALES HISTORY
    # -------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sales_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            quantity_sold INTEGER NOT NULL,
            selling_price_per_unit REAL NOT NULL,
            modal_per_unit REAL NOT NULL,
            revenue REAL NOT NULL,
            total_modal REAL NOT NULL,
            estimated_profit REAL NOT NULL,
            deduct_stock INTEGER DEFAULT 1,
            sold_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES products(id)
        )
    """)


    # Shopee import fields for sales_history (safe migration)
    cursor.execute("PRAGMA table_info(sales_history)")
    sales_columns = {row[1] for row in cursor.fetchall()}

    if "source" not in sales_columns:
        cursor.execute(
            "ALTER TABLE sales_history ADD COLUMN source TEXT DEFAULT 'Manual'"
        )

    if "external_order_id" not in sales_columns:
        cursor.execute(
            "ALTER TABLE sales_history ADD COLUMN external_order_id TEXT"
        )

    if "external_line_key" not in sales_columns:
        cursor.execute(
            "ALTER TABLE sales_history ADD COLUMN external_line_key TEXT"
        )

    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_sales_external_line_key
        ON sales_history(external_line_key)
        WHERE external_line_key IS NOT NULL
    """)

    # Persistent Shopee -> Neomii product mapping
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS shopee_product_mappings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shopee_product_name TEXT NOT NULL,
            shopee_variation_name TEXT NOT NULL DEFAULT '',
            product_id INTEGER NOT NULL,
            UNIQUE(shopee_product_name, shopee_variation_name),
            FOREIGN KEY (product_id) REFERENCES products(id)
        )
    """)


    # -------------------------------------------------
    # REUSABLE OFFCUT RULES
    # -------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS offcut_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_product_id INTEGER NOT NULL,
            source_material_id INTEGER NOT NULL,
            offcut_material_id INTEGER NOT NULL,
            offcuts_per_metre REAL NOT NULL DEFAULT 0,
            FOREIGN KEY (source_product_id) REFERENCES products(id),
            FOREIGN KEY (source_material_id) REFERENCES materials(id),
            FOREIGN KEY (offcut_material_id) REFERENCES materials(id),
            UNIQUE(source_product_id, source_material_id, offcut_material_id)
        )
    """)


    # -------------------------------------------------
    # CATEGORY-WIDE REUSABLE OFFCUT RULES
    # -------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS category_offcut_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_category TEXT NOT NULL,
            source_material_id INTEGER NOT NULL,
            offcut_material_id INTEGER NOT NULL,
            offcuts_per_metre REAL NOT NULL DEFAULT 0,
            FOREIGN KEY (source_material_id) REFERENCES materials(id),
            FOREIGN KEY (offcut_material_id) REFERENCES materials(id),
            UNIQUE(source_category, source_material_id, offcut_material_id)
        )
    """)


    # -------------------------------------------------
    # MATERIAL-CATEGORY OFFCUT TEMPLATE RULES
    # -------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS material_category_offcut_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_product_category TEXT NOT NULL,
            source_material_category TEXT NOT NULL,
            offcuts_per_metre REAL NOT NULL DEFAULT 0,
            offcut_name_suffix TEXT NOT NULL DEFAULT 'Kindle usable offcut',
            UNIQUE(source_product_category, source_material_category)
        )
    """)

    # -------------------------------------------------
    # SHOP SETTINGS
    # -------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS shop_settings (
            id INTEGER PRIMARY KEY,
            shop_name TEXT DEFAULT 'Neomii',
            logo_path TEXT
        )
    """)

    cursor.execute("""
        INSERT OR IGNORE INTO shop_settings (id, shop_name)
        VALUES (1, 'Neomii')
    """)

    conn.commit()
    conn.close()


# =====================================================
# MATERIALS
# =====================================================

def add_material(
    name,
    category,
    unit_price,
    unit,
    fabric_width_cm
):
    """
    Add a material to the price list.

    New materials start with zero stock.
    Stock is added separately through Restock.
    """
    conn = get_connection()
    cursor = conn.cursor()

    method = "Measured" if category in (
        "Fabric",
        "Outer Fabric",
        "Lining Fabric",
        "Batting",
        "Interfacing",
        "Elastic",
        "Velcro",
        "Ribbon",
    ) else "Unit"

    cursor.execute("""
        INSERT INTO materials (
            name,
            category,
            purchase_price,
            purchase_quantity,
            unit,
            fabric_width_cm,
            current_quantity,
            measurement_method,
            average_unit_cost,
            unit_price
        )
        VALUES (?, ?, 0, 0, ?, ?, 0, ?, ?, ?)
    """, (
        name,
        category,
        unit,
        fabric_width_cm,
        method,
        unit_price,
        unit_price
    ))

    conn.commit()
    conn.close()


def get_materials():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM materials
        ORDER BY category, name
    """)

    rows = cursor.fetchall()
    conn.close()

    return rows


def get_material(material_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM materials
        WHERE id = ?
    """, (material_id,))

    row = cursor.fetchone()
    conn.close()

    return row


def update_material(
    material_id,
    name,
    category,
    unit,
    fabric_width_cm,
    current_quantity,
    unit_price
):
    conn = get_connection()
    cursor = conn.cursor()

    method = "Measured" if category in (
        "Fabric",
        "Outer Fabric",
        "Lining Fabric",
        "Batting",
        "Interfacing",
        "Elastic",
        "Velcro",
        "Ribbon",
    ) else "Unit"

    cursor.execute("""
        UPDATE materials
        SET
            name = ?,
            category = ?,
            unit = ?,
            fabric_width_cm = ?,
            current_quantity = ?,
            measurement_method = ?,
            average_unit_cost = ?,
            unit_price = ?
        WHERE id = ?
    """, (
        name,
        category,
        unit,
        fabric_width_cm,
        current_quantity,
        method,
        unit_price,
        unit_price,
        material_id
    ))

    conn.commit()
    conn.close()


def restock_material(material_id, quantity_added):
    """
    Add physical stock only.

    Restocking does not change the price used for modal calculations.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM materials
        WHERE id = ?
    """, (material_id,))

    material = cursor.fetchone()

    if not material:
        conn.close()
        return

    old_quantity = float(material["current_quantity"] or 0)
    new_quantity = float(quantity_added)

    if new_quantity <= 0:
        conn.close()
        return

    combined_quantity = old_quantity + new_quantity

    unit_price = float(
        material["unit_price"]
        if "unit_price" in material.keys() and material["unit_price"] is not None
        else material["average_unit_cost"] or 0
    )

    reference_value = new_quantity * unit_price

    cursor.execute("""
        UPDATE materials
        SET current_quantity = ?
        WHERE id = ?
    """, (
        combined_quantity,
        material_id
    ))

    # Keep using the existing table as restock history.
    cursor.execute("""
        INSERT INTO material_restock_history (
            material_id,
            quantity_added,
            total_cost,
            unit_cost
        )
        VALUES (?, ?, ?, ?)
    """, (
        material_id,
        new_quantity,
        reference_value,
        unit_price
    ))

    conn.commit()
    conn.close()


def get_restock_history(material_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM material_restock_history
        WHERE material_id = ?
        ORDER BY purchased_at DESC, id DESC
    """, (material_id,))

    rows = cursor.fetchall()
    conn.close()

    return rows


def delete_material(material_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        DELETE FROM product_materials
        WHERE material_id = ?
    """, (material_id,))

    cursor.execute("""
        DELETE FROM material_restock_history
        WHERE material_id = ?
    """, (material_id,))

    cursor.execute("""
        DELETE FROM materials
        WHERE id = ?
    """, (material_id,))

    conn.commit()
    conn.close()


# =====================================================
# PRODUCTS
# =====================================================

def add_product(
    category,
    design,
    sku,
    selling_price,
    packaging_cost,
    platform_fee,
    stock,
    image_path,
    status="Active"
):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO products (
            category,
            design,
            sku,
            selling_price,
            packaging_cost,
            platform_fee,
            stock,
            image_path,
            status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        category,
        design,
        sku,
        selling_price,
        packaging_cost,
        platform_fee,
        stock,
        image_path,
        status
    ))

    conn.commit()
    conn.close()


def get_products():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM products
        ORDER BY category, design
    """)

    rows = cursor.fetchall()
    conn.close()

    return rows


def update_product(
    product_id,
    category,
    design,
    sku,
    selling_price,
    packaging_cost,
    platform_fee,
    stock,
    status="Active"
):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE products
        SET
            category = ?,
            design = ?,
            sku = ?,
            selling_price = ?,
            packaging_cost = ?,
            platform_fee = ?,
            stock = ?,
            status = ?
        WHERE id = ?
    """, (
        category,
        design,
        sku,
        selling_price,
        packaging_cost,
        platform_fee,
        stock,
        status,
        product_id
    ))

    conn.commit()
    conn.close()


def delete_product(product_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        DELETE FROM product_materials
        WHERE product_id = ?
    """, (product_id,))

    cursor.execute("""
        DELETE FROM products
        WHERE id = ?
    """, (product_id,))

    conn.commit()
    conn.close()


# =====================================================
# PRODUCT RECIPES
# =====================================================

def add_product_material(
    product_id,
    material_id,
    quantity_used=0,
    pieces_count=0,
    piece_width_cm=0,
    piece_height_cm=0,
    wastage_pct=0,
    yield_per_metre=0
):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO product_materials (
            product_id,
            material_id,
            quantity_used,
            pieces_count,
            piece_width_cm,
            piece_height_cm,
            wastage_pct,
            yield_per_metre
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        product_id,
        material_id,
        quantity_used,
        pieces_count,
        piece_width_cm,
        piece_height_cm,
        wastage_pct,
        yield_per_metre
    ))

    conn.commit()
    conn.close()


def update_product_material_yield(recipe_id, yield_per_metre):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE product_materials
        SET yield_per_metre = ?
        WHERE id = ?
    """, (yield_per_metre, recipe_id))

    conn.commit()
    conn.close()


def get_product_materials(product_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            pm.id,
            pm.product_id,
            pm.material_id,
            pm.quantity_used,
            pm.pieces_count,
            pm.piece_width_cm,
            pm.piece_height_cm,
            pm.wastage_pct,
            pm.yield_per_metre,

            m.name AS material_name,
            m.category AS material_category,
            m.purchase_price,
            m.purchase_quantity,
            m.unit,
            m.fabric_width_cm,
            m.current_quantity,
            m.measurement_method,
            m.average_unit_cost,
            m.unit_price

        FROM product_materials pm

        JOIN materials m
            ON pm.material_id = m.id

        WHERE pm.product_id = ?

        ORDER BY m.category, m.name
    """, (product_id,))

    rows = cursor.fetchall()
    conn.close()

    return rows


def delete_product_material(recipe_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        DELETE FROM product_materials
        WHERE id = ?
    """, (recipe_id,))

    conn.commit()
    conn.close()




# =====================================================
# PRODUCTION
# =====================================================

def record_production(product_id, quantity_produced, material_deductions, offcut_additions=None):
    quantity_produced = int(quantity_produced)
    offcut_additions = offcut_additions or []

    if quantity_produced <= 0:
        return False, "Production quantity must be more than zero."

    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("BEGIN IMMEDIATE")

        cursor.execute(
            "SELECT * FROM products WHERE id = ?",
            (product_id,)
        )
        product = cursor.fetchone()

        if not product:
            conn.rollback()
            return False, "Product could not be found."

        for deduction in material_deductions:
            material_id = int(deduction["material_id"])
            required = float(deduction["quantity_used"])

            cursor.execute(
                "SELECT * FROM materials WHERE id = ?",
                (material_id,)
            )
            material = cursor.fetchone()

            if not material:
                conn.rollback()
                return False, "One of the recipe materials could not be found."

            available = float(material["current_quantity"] or 0)

            if required < 0:
                conn.rollback()
                return False, "Invalid material deduction."

            if available + 1e-9 < required:
                conn.rollback()
                return (
                    False,
                    f"Not enough {material['name']}. "
                    f"Required {required:.3f}, available {available:.3f}."
                )

        cursor.execute("""
            INSERT INTO production_history (
                product_id,
                quantity_produced
            )
            VALUES (?, ?)
        """, (
            product_id,
            quantity_produced
        ))

        production_id = cursor.lastrowid

        for deduction in material_deductions:
            material_id = int(deduction["material_id"])
            required = float(deduction["quantity_used"])
            unit = deduction.get("unit") or ""

            cursor.execute("""
                UPDATE materials
                SET current_quantity = current_quantity - ?
                WHERE id = ?
            """, (
                required,
                material_id
            ))

            cursor.execute("""
                INSERT INTO production_material_usage (
                    production_id,
                    material_id,
                    quantity_used,
                    unit
                )
                VALUES (?, ?, ?, ?)
            """, (
                production_id,
                material_id,
                required,
                unit
            ))

        cursor.execute("""
            UPDATE products
            SET stock = stock + ?
            WHERE id = ?
        """, (
            quantity_produced,
            product_id
        ))

        # Add reusable offcuts generated by this production batch.
        for addition in offcut_additions:
            offcut_material_id = int(addition["material_id"])
            quantity_generated = float(addition["quantity_generated"])

            if quantity_generated < 0:
                conn.rollback()
                return False, "Invalid offcut quantity."

            cursor.execute(
                "SELECT * FROM materials WHERE id = ?",
                (offcut_material_id,)
            )
            offcut_material = cursor.fetchone()

            if not offcut_material:
                conn.rollback()
                return False, "An offcut material could not be found."

            cursor.execute("""
                UPDATE materials
                SET current_quantity = current_quantity + ?
                WHERE id = ?
            """, (
                quantity_generated,
                offcut_material_id
            ))

        conn.commit()
        return True, production_id

    except Exception as exc:
        conn.rollback()
        return False, str(exc)

    finally:
        conn.close()


def get_production_history(limit=50):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            ph.id,
            ph.product_id,
            ph.quantity_produced,
            ph.produced_at,
            p.design,
            p.category,
            p.sku
        FROM production_history ph
        JOIN products p
            ON ph.product_id = p.id
        ORDER BY ph.produced_at DESC, ph.id DESC
        LIMIT ?
    """, (int(limit),))

    rows = cursor.fetchall()
    conn.close()

    return rows


def get_production_material_usage(production_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            pmu.id,
            pmu.production_id,
            pmu.material_id,
            pmu.quantity_used,
            pmu.unit,
            m.name AS material_name,
            m.category AS material_category
        FROM production_material_usage pmu
        JOIN materials m
            ON pmu.material_id = m.id
        WHERE pmu.production_id = ?
        ORDER BY m.category, m.name
    """, (production_id,))

    rows = cursor.fetchall()
    conn.close()

    return rows




# =====================================================
# SALES
# =====================================================

def record_sale(
    product_id,
    quantity_sold,
    selling_price_per_unit,
    modal_per_unit,
    deduct_stock=True
):
    quantity_sold = int(quantity_sold)
    selling_price_per_unit = float(selling_price_per_unit)
    modal_per_unit = float(modal_per_unit)

    if quantity_sold <= 0:
        return False, "Sale quantity must be more than zero."

    revenue = selling_price_per_unit * quantity_sold
    total_modal = modal_per_unit * quantity_sold
    estimated_profit = revenue - total_modal

    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("BEGIN IMMEDIATE")

        cursor.execute(
            "SELECT * FROM products WHERE id = ?",
            (product_id,)
        )
        product = cursor.fetchone()

        if not product:
            conn.rollback()
            return False, "Product could not be found."

        current_stock = int(product["stock"] or 0)

        if deduct_stock and current_stock < quantity_sold:
            conn.rollback()
            return (
                False,
                f"Not enough finished stock. "
                f"Available: {current_stock}, sale quantity: {quantity_sold}."
            )

        cursor.execute("""
            INSERT INTO sales_history (
                product_id,
                quantity_sold,
                selling_price_per_unit,
                modal_per_unit,
                revenue,
                total_modal,
                estimated_profit,
                deduct_stock
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            product_id,
            quantity_sold,
            selling_price_per_unit,
            modal_per_unit,
            revenue,
            total_modal,
            estimated_profit,
            1 if deduct_stock else 0
        ))

        sale_id = cursor.lastrowid

        if deduct_stock:
            cursor.execute("""
                UPDATE products
                SET stock = stock - ?
                WHERE id = ?
            """, (
                quantity_sold,
                product_id
            ))

        conn.commit()
        return True, sale_id

    except Exception as exc:
        conn.rollback()
        return False, str(exc)

    finally:
        conn.close()


def get_sales_history(limit=100):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            sh.id,
            sh.product_id,
            sh.quantity_sold,
            sh.selling_price_per_unit,
            sh.modal_per_unit,
            sh.revenue,
            sh.total_modal,
            sh.estimated_profit,
            sh.deduct_stock,
            sh.sold_at,
            p.design,
            p.category,
            p.sku
        FROM sales_history sh
        JOIN products p
            ON sh.product_id = p.id
        ORDER BY sh.sold_at DESC, sh.id DESC
        LIMIT ?
    """, (int(limit),))

    rows = cursor.fetchall()
    conn.close()
    return rows




# =====================================================
# SHOPEE IMPORT
# =====================================================

def get_shopee_mappings():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            spm.id,
            spm.shopee_product_name,
            spm.shopee_variation_name,
            spm.product_id,
            p.category,
            p.design,
            p.sku
        FROM shopee_product_mappings spm
        JOIN products p ON p.id = spm.product_id
        ORDER BY spm.shopee_product_name, spm.shopee_variation_name
    """)
    rows = cursor.fetchall()
    conn.close()
    return rows


def save_shopee_mapping(shopee_product_name, shopee_variation_name, product_id):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO shopee_product_mappings (
                shopee_product_name,
                shopee_variation_name,
                product_id
            )
            VALUES (?, ?, ?)
            ON CONFLICT(shopee_product_name, shopee_variation_name)
            DO UPDATE SET product_id = excluded.product_id
        """, (
            str(shopee_product_name or "").strip(),
            str(shopee_variation_name or "").strip(),
            int(product_id)
        ))
        conn.commit()
        return True, None
    except Exception as exc:
        conn.rollback()
        return False, str(exc)
    finally:
        conn.close()


def shopee_line_already_imported(external_line_key):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT 1 FROM sales_history WHERE external_line_key = ? LIMIT 1",
        (external_line_key,)
    )
    exists = cursor.fetchone() is not None
    conn.close()
    return exists


def import_shopee_sale(
    product_id,
    quantity_sold,
    selling_price_per_unit,
    modal_per_unit,
    sold_at,
    external_order_id,
    external_line_key,
    deduct_stock=False
):
    quantity_sold = int(quantity_sold)
    selling_price_per_unit = float(selling_price_per_unit)
    modal_per_unit = float(modal_per_unit)

    if quantity_sold <= 0:
        return False, "Sale quantity must be more than zero."

    revenue = selling_price_per_unit * quantity_sold
    total_modal = modal_per_unit * quantity_sold
    estimated_profit = revenue - total_modal

    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("BEGIN IMMEDIATE")

        cursor.execute("SELECT * FROM products WHERE id = ?", (product_id,))
        product = cursor.fetchone()
        if not product:
            conn.rollback()
            return False, "Product could not be found."

        cursor.execute(
            "SELECT 1 FROM sales_history WHERE external_line_key = ? LIMIT 1",
            (external_line_key,)
        )
        if cursor.fetchone():
            conn.rollback()
            return False, "Already imported"

        current_stock = int(product["stock"] or 0)
        if deduct_stock and current_stock < quantity_sold:
            conn.rollback()
            return False, (
                f"Not enough finished stock. Available: {current_stock}, "
                f"sale quantity: {quantity_sold}."
            )

        cursor.execute("""
            INSERT INTO sales_history (
                product_id,
                quantity_sold,
                selling_price_per_unit,
                modal_per_unit,
                revenue,
                total_modal,
                estimated_profit,
                deduct_stock,
                sold_at,
                source,
                external_order_id,
                external_line_key
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'Shopee Import', ?, ?)
        """, (
            int(product_id),
            quantity_sold,
            selling_price_per_unit,
            modal_per_unit,
            revenue,
            total_modal,
            estimated_profit,
            1 if deduct_stock else 0,
            sold_at,
            str(external_order_id or ""),
            str(external_line_key)
        ))

        sale_id = cursor.lastrowid

        if deduct_stock:
            cursor.execute(
                "UPDATE products SET stock = stock - ? WHERE id = ?",
                (quantity_sold, int(product_id))
            )

        conn.commit()
        return True, sale_id

    except Exception as exc:
        conn.rollback()
        return False, str(exc)
    finally:
        conn.close()





# =====================================================
# REUSABLE OFFCUTS
# =====================================================

def create_offcut_material(name):
    """Create a zero-cost reusable offcut inventory item if it does not exist."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM materials
        WHERE LOWER(TRIM(name)) = LOWER(TRIM(?))
          AND category = 'Reusable Offcut'
        LIMIT 1
    """, (name,))
    existing = cursor.fetchone()

    if existing:
        conn.close()
        return int(existing["id"])

    cursor.execute("""
        INSERT INTO materials (
            name,
            category,
            purchase_price,
            purchase_quantity,
            unit,
            fabric_width_cm,
            current_quantity,
            measurement_method,
            average_unit_cost,
            unit_price
        )
        VALUES (?, 'Reusable Offcut', 0, 0, 'set', 0, 0, 'Unit', 0, 0)
    """, (name,))

    material_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return material_id


def add_offcut_rule(
    source_product_id,
    source_material_id,
    offcut_material_id,
    offcuts_per_metre
):
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT INTO offcut_rules (
                source_product_id,
                source_material_id,
                offcut_material_id,
                offcuts_per_metre
            )
            VALUES (?, ?, ?, ?)
            ON CONFLICT(
                source_product_id,
                source_material_id,
                offcut_material_id
            )
            DO UPDATE SET offcuts_per_metre = excluded.offcuts_per_metre
        """, (
            int(source_product_id),
            int(source_material_id),
            int(offcut_material_id),
            float(offcuts_per_metre)
        ))
        conn.commit()
        return True, None
    except Exception as exc:
        conn.rollback()
        return False, str(exc)
    finally:
        conn.close()


def get_offcut_rules(source_product_id=None):
    conn = get_connection()
    cursor = conn.cursor()

    sql = """
        SELECT
            r.id,
            r.source_product_id,
            r.source_material_id,
            r.offcut_material_id,
            r.offcuts_per_metre,
            p.category AS source_product_category,
            p.design AS source_product_design,
            sm.name AS source_material_name,
            om.name AS offcut_material_name,
            om.current_quantity AS offcut_current_quantity
        FROM offcut_rules r
        JOIN products p ON p.id = r.source_product_id
        JOIN materials sm ON sm.id = r.source_material_id
        JOIN materials om ON om.id = r.offcut_material_id
    """
    params = []

    if source_product_id is not None:
        sql += " WHERE r.source_product_id = ?"
        params.append(int(source_product_id))

    sql += " ORDER BY p.category, p.design, sm.name"

    cursor.execute(sql, params)
    rows = cursor.fetchall()
    conn.close()
    return rows


def delete_offcut_rule(rule_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM offcut_rules WHERE id = ?", (int(rule_id),))
    conn.commit()
    conn.close()




def add_category_offcut_rule(
    source_category,
    source_material_id,
    offcut_material_id,
    offcuts_per_metre
):
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT INTO category_offcut_rules (
                source_category,
                source_material_id,
                offcut_material_id,
                offcuts_per_metre
            )
            VALUES (?, ?, ?, ?)
            ON CONFLICT(
                source_category,
                source_material_id,
                offcut_material_id
            )
            DO UPDATE SET offcuts_per_metre = excluded.offcuts_per_metre
        """, (
            str(source_category),
            int(source_material_id),
            int(offcut_material_id),
            float(offcuts_per_metre)
        ))

        conn.commit()
        return True, None

    except Exception as exc:
        conn.rollback()
        return False, str(exc)

    finally:
        conn.close()


def get_category_offcut_rules(source_category=None):
    conn = get_connection()
    cursor = conn.cursor()

    sql = """
        SELECT
            r.id,
            r.source_category,
            r.source_material_id,
            r.offcut_material_id,
            r.offcuts_per_metre,
            sm.name AS source_material_name,
            om.name AS offcut_material_name,
            om.current_quantity AS offcut_current_quantity
        FROM category_offcut_rules r
        JOIN materials sm
            ON sm.id = r.source_material_id
        JOIN materials om
            ON om.id = r.offcut_material_id
    """

    params = []

    if source_category is not None:
        sql += " WHERE r.source_category = ?"
        params.append(str(source_category))

    sql += " ORDER BY r.source_category, sm.name"

    cursor.execute(sql, params)
    rows = cursor.fetchall()
    conn.close()

    return rows


def delete_category_offcut_rule(rule_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM category_offcut_rules WHERE id = ?",
        (int(rule_id),)
    )

    conn.commit()
    conn.close()



def add_material_category_offcut_rule(source_product_category, source_material_category, offcuts_per_metre, offcut_name_suffix="Kindle usable offcut"):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO material_category_offcut_rules
            (source_product_category, source_material_category, offcuts_per_metre, offcut_name_suffix)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(source_product_category, source_material_category)
            DO UPDATE SET offcuts_per_metre=excluded.offcuts_per_metre,
                          offcut_name_suffix=excluded.offcut_name_suffix
        """, (str(source_product_category), str(source_material_category),
              float(offcuts_per_metre), str(offcut_name_suffix)))
        conn.commit()

        # Immediately create the reusable-offcut inventory items for all
        # existing materials covered by this rule, so they are available
        # in Product Recipe before any production is recorded.
        conn.close()
        ensure_material_category_offcuts(
            source_product_category,
            source_material_category
        )
        return True, None
    except Exception as exc:
        conn.rollback()
        return False, str(exc)
    finally:
        conn.close()


def get_material_category_offcut_rules(source_product_category=None):
    conn = get_connection()
    cursor = conn.cursor()
    sql = "SELECT * FROM material_category_offcut_rules"
    params = []
    if source_product_category is not None:
        sql += " WHERE source_product_category = ?"
        params.append(str(source_product_category))
    sql += " ORDER BY source_product_category, source_material_category"
    cursor.execute(sql, params)
    rows = cursor.fetchall()
    conn.close()
    return rows



def ensure_material_category_offcuts(
    source_product_category=None,
    source_material_category=None
):
    """
    Create zero-cost Reusable Offcut inventory items for existing materials
    covered by material-category rules.

    Example:
      Book Sleeve + Outer Fabric rule
      -> Blue Coquette — Kindle usable offcut
      -> Pink Bunny — Kindle usable offcut
      -> etc.

    Safe to run repeatedly; existing offcut materials are reused.
    """
    rules = get_material_category_offcut_rules(source_product_category)

    created_ids = []

    conn = get_connection()
    cursor = conn.cursor()

    for rule in rules:
        if (
            source_material_category is not None
            and str(rule["source_material_category"]) != str(source_material_category)
        ):
            continue

        cursor.execute("""
            SELECT DISTINCT m.id
            FROM products p
            JOIN product_materials pm
                ON pm.product_id = p.id
            JOIN materials m
                ON m.id = pm.material_id
            WHERE p.category = ?
              AND m.category = ?
        """, (
            rule["source_product_category"],
            rule["source_material_category"]
        ))

        source_material_ids = [
            int(row["id"])
            for row in cursor.fetchall()
        ]

        for source_material_id in source_material_ids:
            offcut_id = get_or_create_named_offcut_material(
                source_material_id,
                rule["offcut_name_suffix"]
            )
            if offcut_id is not None:
                created_ids.append(int(offcut_id))

    conn.close()
    return created_ids


def delete_material_category_offcut_rule(rule_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM material_category_offcut_rules WHERE id = ?", (int(rule_id),))
    conn.commit()
    conn.close()


def get_or_create_named_offcut_material(source_material_id, suffix):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM materials WHERE id = ?", (int(source_material_id),))
    source = cursor.fetchone()
    if not source:
        conn.close()
        return None

    offcut_name = f"{source['name']} — {suffix}"
    cursor.execute("""
        SELECT id FROM materials
        WHERE LOWER(TRIM(name)) = LOWER(TRIM(?))
          AND category = 'Reusable Offcut'
        LIMIT 1
    """, (offcut_name,))
    existing = cursor.fetchone()

    if existing:
        material_id = int(existing["id"])
        conn.close()
        return material_id

    cursor.execute("""
        INSERT INTO materials
        (name, category, purchase_price, purchase_quantity, unit,
         fabric_width_cm, current_quantity, measurement_method,
         average_unit_cost, unit_price)
        VALUES (?, 'Reusable Offcut', 0, 0, 'set', 0, 0, 'Unit', 0, 0)
    """, (offcut_name,))
    material_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return material_id


def get_offcut_generation_for_production(product_id, material_deductions):
    """
    Preview reusable offcuts from:
    1) product-specific rules
    2) exact-material category-wide rules
    3) material-category template rules

    Template rules preserve each fabric separately. For example:
    Pink Bunny outer fabric -> Pink Bunny outer fabric — Kindle usable offcut
    Forest outer fabric     -> Forest outer fabric — Kindle usable offcut
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT category FROM products WHERE id = ?",
        (int(product_id),)
    )
    product = cursor.fetchone()

    if not product:
        conn.close()
        return []

    deduction_by_material = {
        int(d["material_id"]): float(d["quantity_used"])
        for d in material_deductions
    }

    # Get material metadata for deducted items.
    material_meta = {}
    if deduction_by_material:
        placeholders = ",".join(["?"] * len(deduction_by_material))
        cursor.execute(
            f"""
            SELECT id, name, category
            FROM materials
            WHERE id IN ({placeholders})
            """,
            tuple(deduction_by_material.keys())
        )
        for row in cursor.fetchall():
            material_meta[int(row["id"])] = row

    conn.close()

    product_rules = get_offcut_rules(product_id)
    exact_category_rules = get_category_offcut_rules(product["category"])
    template_rules = get_material_category_offcut_rules(product["category"])

    generated = []
    seen_source_materials = set()

    # 1) Product-specific rules take highest priority.
    for rule in product_rules:
        source_material_id = int(rule["source_material_id"])
        metres_used = deduction_by_material.get(source_material_id, 0.0)
        qty = metres_used * float(rule["offcuts_per_metre"] or 0)

        if metres_used > 0 and qty > 0:
            generated.append({
                "offcut_material_id": int(rule["offcut_material_id"]),
                "offcut_material_name": rule["offcut_material_name"],
                "quantity_generated": qty,
                "source_material_name": rule["source_material_name"],
                "metres_used": metres_used,
                "offcuts_per_metre": float(rule["offcuts_per_metre"] or 0),
            })
            seen_source_materials.add(source_material_id)

    # 2) Existing exact-material category rules.
    for rule in exact_category_rules:
        source_material_id = int(rule["source_material_id"])
        if source_material_id in seen_source_materials:
            continue

        metres_used = deduction_by_material.get(source_material_id, 0.0)
        qty = metres_used * float(rule["offcuts_per_metre"] or 0)

        if metres_used > 0 and qty > 0:
            generated.append({
                "offcut_material_id": int(rule["offcut_material_id"]),
                "offcut_material_name": rule["offcut_material_name"],
                "quantity_generated": qty,
                "source_material_name": rule["source_material_name"],
                "metres_used": metres_used,
                "offcuts_per_metre": float(rule["offcuts_per_metre"] or 0),
            })
            seen_source_materials.add(source_material_id)

    # 3) Material-category templates.
    for rule in template_rules:
        wanted_category = str(rule["source_material_category"])
        rate = float(rule["offcuts_per_metre"] or 0)
        suffix = str(rule["offcut_name_suffix"] or "Kindle usable offcut")

        for material_id, metres_used in deduction_by_material.items():
            if material_id in seen_source_materials:
                continue

            meta = material_meta.get(material_id)
            if not meta or str(meta["category"]) != wanted_category:
                continue

            qty = metres_used * rate
            if metres_used <= 0 or qty <= 0:
                continue

            offcut_material_id = get_or_create_named_offcut_material(
                material_id,
                suffix
            )
            if offcut_material_id is None:
                continue

            conn2 = get_connection()
            cursor2 = conn2.cursor()
            cursor2.execute(
                "SELECT name FROM materials WHERE id = ?",
                (offcut_material_id,)
            )
            offcut_row = cursor2.fetchone()
            conn2.close()

            generated.append({
                "offcut_material_id": int(offcut_material_id),
                "offcut_material_name": offcut_row["name"],
                "quantity_generated": qty,
                "source_material_name": meta["name"],
                "metres_used": metres_used,
                "offcuts_per_metre": rate,
            })
            seen_source_materials.add(material_id)

    return generated
# =====================================================
# SHOP SETTINGS
# =====================================================

def get_shop_settings():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM shop_settings
        WHERE id = 1
    """)

    row = cursor.fetchone()
    conn.close()

    return row


def update_shop_settings(shop_name, logo_path):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE shop_settings
        SET
            shop_name = ?,
            logo_path = ?
        WHERE id = 1
    """, (
        shop_name,
        logo_path
    ))

    conn.commit()
    conn.close()