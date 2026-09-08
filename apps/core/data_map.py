"""Static map of the stores this ERP talks to. Explains, does not query."""

STORES = (
    {
        "id": "mssql",
        "title": "Live iadmin",
        "kind": "SQL Server",
        "where": "mssql.tag11.in:1232 / stock_rfid",
        "role": "What staff still type into Sonal's iadmin. Sync only reads this. It never writes back.",
    },
    {
        "id": "local",
        "title": "This computer",
        "kind": "Postgres",
        "where": "pj_erp_prod and pj_erp_dev",
        "role": "The catalogs on this machine. /dev/db-sync/ Sync now writes only the active one (see the badge).",
    },
    {
        "id": "render",
        "title": "Live website",
        "kind": "Postgres on Render",
        "where": "pjsystems.itsshin.dev · database pj_erp_db",
        "role": "What the deployed site searches. A local sync does not touch this. The webhook does.",
    },
    {
        "id": "sheet",
        "title": "DATAFILE.xlsx",
        "kind": "Tiara print sheet",
        "where": "Google Sheet they still print from",
        "role": "The list they trust for tags. Metal type, purity, and net weight are typed here. Not loaded by sync.",
    },
)

FLOW = (
    {
        "step": "1",
        "title": "Design",
        "legacy": "tblproduct_master",
        "django": "catalogue.ProductMaster",
        "note": "Style, reference, price. Net weight and metal on this table are often empty.",
    },
    {
        "step": "2",
        "title": "Piece",
        "legacy": "tblproduct_detail_master",
        "django": "inventory.ProductItem",
        "note": "One barcode (PJ#####). Location and sold/assigned status live here.",
    },
    {
        "step": "3",
        "title": "Metal row",
        "legacy": "tbljewellery_metal_details",
        "django": "gold_weight / net_weight number only",
        "note": "Weight text is real. metal_id and metal_purity_id are numbers shared by several lookup tables — do not treat them as names.",
    },
    {
        "step": "4",
        "title": "Print sheet",
        "legacy": "DATAFILE.xlsx",
        "django": "not imported yet",
        "note": "Owner YZC1, Metal Purity 18K, Net Weight 1.58g. This is what they print in TiaraHub.",
    },
)

SYNCED = (
    ("Products", "tblproduct_master", "ProductMaster", "Copied"),
    ("Items / barcodes", "tblproduct_detail_master", "ProductItem", "Copied"),
    ("Locations", "tblcompany_locations", "Location", "Copied"),
    ("Categories", "tbljewellery_type", "Category", "Copied"),
    ("Suppliers", "tblvendor_type", "Supplier", "Copied"),
    ("Resellers", "tblResellerMaster", "Reseller", "Copied"),
    ("Invoices", "tblProductAssignMaster", "AssignmentMaster", "Copied"),
    ("Invoice lines", "tblProductAssign", "AssignmentLine", "Copied"),
    ("Reseller payments", "tblAssignPayment_transaction", "ResellerPayment", "Copied"),
    ("Metal weight number", "tbljewellery_metal_details.weight", "gold_weight, net_weight if empty", "Number only"),
    ("Diamond weight number", "tbljewellery_stone_details.weight", "diamond_weight", "Only diamond subcats"),
)

NOT_COPIED = (
    ("Metal / karat names", "Overlapping ids on metal details, plus DATAFILE Metal Type / Metal Purity", "Reports disagree. Sheet is the print source. Names are not synced."),
    ("Tag print sheet", "DATAFILE.xlsx", "Not a database. 226 China rows are owner YZC1, PJ24881–PJ25106."),
    ("Label print history", "—", "Written here when BrowserPrint succeeds. Not in iadmin."),
    ("TiaraHub RFID encode", "Printed outside this app", "They still print from the sheet until tag layout is locked here."),
)

# Legacy stock_rfid has almost no real foreign keys. These are the join
# columns the reports and our sync actually use. "loose" means the same
# integer is reused by more than one lookup table.
LEGACY_TABLES = (
    {
        "name": "tblproduct_master",
        "pk": "nid",
        "holds": "Design / style. reference_id, product_Name, selling_price, category, vendor_id.",
        "links": (
            "category → tbljewellery_type.nid",
            "vendor_id → tblvendor_type.nid",
            "company_locationid → tblcompany_locations.nid",
            "metal / metal_purity_id usually empty",
        ),
    },
    {
        "name": "tblproduct_detail_master",
        "pk": "nid",
        "holds": "One physical piece. barcode_number is the PJ code.",
        "links": (
            "product_masterid → tblproduct_master.nid",
            "barcode_number = DATAFILE RFID Tag",
        ),
    },
    {
        "name": "tbljewellery_metal_details",
        "pk": "nid",
        "holds": "Weight text and numeric metal/purity ids. Not a name.",
        "links": (
            "product_id → tblproduct_master.nid",
            "metal_id → tblmetalcountry_master.nid (loose)",
            "metal_purity_id → tblMetalpurity_master.nid or tblpurity_country_mgmt.nid (loose)",
        ),
    },
    {
        "name": "tbljewellery_stone_details",
        "pk": "nid",
        "holds": "Stone weight and subcategory id. Often a different story than the metal row.",
        "links": (
            "product_id → tblproduct_master.nid",
            "stone_subcat_id → tblstone_sub_category",
        ),
    },
    {
        "name": "tblpurity_country_mgmt",
        "pk": "nid",
        "holds": "Combo row used by some reports to print 18K-Japan Gold.",
        "links": (
            "purity_id → tblMetalpurity_master.nid",
            "country_id → tblmetalcountry_master.nid",
        ),
    },
    {
        "name": "tblProductAssignMaster",
        "pk": "nid",
        "holds": "Invoice header (RE… / RN…).",
        "links": (
            "reseller → tblResellerMaster.nid",
        ),
    },
    {
        "name": "tblProductAssign",
        "pk": "nid",
        "holds": "Invoice line. Tied to a barcode, not only a design.",
        "links": (
            "assign master id → tblProductAssignMaster.nid",
            "barcode → tblproduct_detail_master.barcode_number",
        ),
    },
)

DJANGO_TABLES = (
    {
        "name": "catalogue_productmaster",
        "pk": "id",
        "holds": "Design. legacy_id = tblproduct_master.nid.",
        "links": (
            "category_id → catalogue_category",
            "supplier_id → catalogue_supplier",
            "currency_id → catalogue_currency",
            "metal_id → catalogue_metal (optional, often empty)",
            "purity_id → catalogue_purity (optional, often empty)",
        ),
    },
    {
        "name": "inventory_productitem",
        "pk": "id",
        "holds": "Piece. barcode is unique. legacy_id = tblproduct_detail_master.nid.",
        "links": (
            "product_id → catalogue_productmaster",
            "location_id → locations_location",
        ),
    },
    {
        "name": "assignment_assignmentmaster",
        "pk": "id",
        "holds": "Invoice. legacy_id = tblProductAssignMaster.nid.",
        "links": (
            "reseller_id → assignment_reseller",
        ),
    },
    {
        "name": "assignment_assignmentline",
        "pk": "id",
        "holds": "One piece on an invoice.",
        "links": (
            "master_id → assignment_assignmentmaster",
            "item_id → inventory_productitem",
        ),
    },
    {
        "name": "payments_resellerpayment",
        "pk": "id",
        "holds": "Payment against an invoice.",
        "links": (
            "assignment_id → assignment_assignmentmaster",
        ),
    },
    {
        "name": "catalogue_productimage",
        "pk": "id",
        "holds": "Photo of a design. Not from iadmin sync.",
        "links": (
            "product_id → catalogue_productmaster",
        ),
    },
)

REL_CHAINS = (
    {
        "title": "Legacy — how a barcode hangs off a design",
        "kind": "legacy",
        "nodes": (
            "tbljewellery_type",
            "tblproduct_master",
            "tblproduct_detail_master",
            "tbljewellery_metal_details",
        ),
        "joins": (
            "type.nid = product.category",
            "detail.product_masterid = product.nid",
            "metal.product_id = product.nid",
            "detail.barcode_number is the PJ code",
        ),
    },
    {
        "title": "Django — real foreign keys",
        "kind": "django",
        "nodes": (
            "catalogue_category",
            "catalogue_productmaster",
            "inventory_productitem",
            "locations_location",
        ),
        "joins": (
            "product.category_id → category.id",
            "item.product_id → product.id",
            "item.location_id → location.id",
            "item.barcode is unique",
        ),
    },
)

ID_TRAP = (
    {
        "id": "1",
        "as_country": "Silver",
        "as_purity": "24K",
        "as_combo": "18K + Japan Gold",
    },
)
