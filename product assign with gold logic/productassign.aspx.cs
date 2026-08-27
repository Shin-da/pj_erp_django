using DocumentFormat.OpenXml.Drawing.Spreadsheet;
using DocumentFormat.OpenXml.Wordprocessing;
using iText.StyledXmlParser.Jsoup.Select;
using Mysqlx.Crud;
using System;
using System.Activities.Expressions;
using System.Activities.Statements;
using System.Collections.Generic;
using System.Data;
using System.Data.OleDb;
using System.Drawing;
using System.Drawing.Imaging;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Security.Policy;
using System.Web.DynamicData;
using System.Web.UI;
using System.Web.UI.WebControls;
using ZXing;
using ZXing.Common;
using WebListItem = System.Web.UI.WebControls.ListItem;



public partial class productassign : System.Web.UI.Page
{
    DataAccess objda = new DataAccess();
    DataSet ds = new DataSet();
    Global_Syncdata oSyncdata = new Global_Syncdata();
    public string action_type = "";
    int row_index = 1;


    protected void Page_Load(object sender, EventArgs e)
    {
        objda.role = "28";
        if (!objda.validateuserrole())
        {
            Response.Redirect("sitehome.aspx?auth=fail");
        }

        if (!IsPostBack)
        {
            mview.ActiveViewIndex = 0;
            bindgrid();
            fillmaster();

        }
    }

    protected void fillroom()
    {
        string query = @"WITH CTE AS
(
    SELECT
        K.*,
        A.nid AS allot_nid,
        A.Employee_ID,
        A.allotment_status,
        A.creationdate AS allot_creationdate,

        ROW_NUMBER() OVER
        (
            PARTITION BY K.id
            ORDER BY A.creationdate DESC
        ) AS rn

    FROM tblRoomMaster K
    LEFT JOIN tblRoomAllotmentMaster A
        ON A.Room_ID = K.id
        AND A.bstatus = 1

    WHERE K.active_status = 'active'
)

SELECT *
FROM CTE
WHERE rn = 1";


        DataSet ds = objda.getdata(query);

        drproomnumber.DataSource = ds;
        drproomnumber.DataTextField = "id";
        drproomnumber.DataValueField = "nid";
        drproomnumber.DataBind();
        drproomnumber.Items.Insert(0, new System.Web.UI.WebControls.ListItem("Select Room", ""));
    }
    public void bindgrid()
    {

        ds = objda.getdata(generatequery("view"));
        if (ds.Tables[0].Rows.Count > 0)
        {
            getpageindex(ds.Tables[0].Rows.Count);
            grvAssign.DataSource = ds;
            grvAssign.DataBind();
            ViewState["assigntable"] = ds.Tables[0];
        }
        drpReseller.Enabled = true;
        txtDate.ReadOnly = false;
    }
    protected void grview2_RowDataBound(object sender, GridViewRowEventArgs e)
    {
        if (e.Row.RowType == DataControlRowType.DataRow)
        {
            HiddenField hidCancelStatus = (HiddenField)e.Row.FindControl("hidinvoicecanclestatus");

            Button btnCancel = (Button)e.Row.FindControl("btnCancelInvoice");
            Button btnInvoice = (Button)e.Row.FindControl("btnViewInvoice");
            LinkButton btnEdit = (LinkButton)e.Row.FindControl("btnEdit");

            string status = "";

            if (hidCancelStatus != null && !string.IsNullOrEmpty(hidCancelStatus.Value))
            {
                status = hidCancelStatus.Value.ToLower();
            }


            if (status == "" || status == "rejected")
            {
                if (btnCancel != null)
                {
                    btnCancel.Text = "Cancel Invoice";
                    btnCancel.Enabled = true;
                }

                if (btnEdit != null)
                    btnEdit.Enabled = true;

                if (btnInvoice != null)
                    btnInvoice.Enabled = true;
            }

            else if (status == "apply")
            {
                if (btnCancel != null)
                {
                    btnCancel.Text = "Cancel Request Sent";
                    btnCancel.Enabled = false;
                    btnCancel.BackColor = System.Drawing.Color.Gray;
                }

                if (btnEdit != null)
                    btnEdit.Enabled = false;

                if (btnInvoice != null)
                    btnInvoice.Enabled = false;
            }

            else if (status == "approved")
            {
                if (btnCancel != null)
                {
                    btnCancel.Text = "Already Cancelled";
                    btnCancel.Enabled = false;
                    btnCancel.BackColor = System.Drawing.Color.Gray;
                }

                if (btnEdit != null)
                    btnEdit.Enabled = false;

                if (btnInvoice != null)
                    btnInvoice.Enabled = false;
            }
        }
    }
    protected void btn_payment_click(object sender, EventArgs e)
    {
        Button btn = (Button)sender;
        string nid = btn.CommandArgument;


        Response.Redirect("assign_paymentpage.aspx?masterid=" + nid);
    }
    public string generatequery(string type)
    {
        string sql = @"
SELECT 
    *,

    -- Sold Quantity
    (
        SELECT SUM(CAST(soldqty AS DECIMAL(18,4)))
        FROM tblProductAssign
        WHERE return_status = 'complete'
          AND master_id = A.nid
    ) AS sold_quantity,

    -- Pending Quantity
    (
        SELECT SUM(CAST(quantity AS DECIMAL(18,4)))
        FROM tblProductAssign
        WHERE return_status = 'pending'
          AND master_id = A.nid
    ) AS pending_quantity,

 CASE
    -- Fully Paid
    WHEN EXISTS
    (
        SELECT 1
        FROM tblAssignPayment_transaction T
        WHERE T.assign_masterid = A.nid
          AND CAST(T.rem_amount AS DECIMAL(18,2)) < 1
    )
    THEN 'complete'

    -- Partially Paid
    WHEN ISNULL(
    (
        SELECT SUM(CAST(ISNULL(T.paid_amount,0) AS DECIMAL(18,2)))
        FROM tblAssignPayment_transaction T
        WHERE T.assign_masterid = A.nid
    ),0) > 1
    THEN 'partial'

    -- Cleared
    WHEN ISNULL(
    (
        SELECT SUM(CAST(soldqty AS DECIMAL(18,4)))
        FROM tblProductAssign
        WHERE return_status = 'complete'
          AND master_id = A.nid
    ),0) = 0
    AND EXISTS
    (
        SELECT 1
        FROM tblProductAssign
        WHERE return_status = 'complete'
          AND master_id = A.nid
    )
    THEN 'Cleared'

    ELSE 'pending'
END AS payment

FROM tblProductAssignMaster A
INNER JOIN tblResellerMaster C
    ON C.NID = A.reseller_id
WHERE A.bstatus = 1 and A.invoice_status!='Cancel'
";

        string condition = "";


        if (drpname.SelectedIndex > 0)
        {
            string val = objda.validate_search_parameter(drpname.SelectedItem.Text);
            condition += " AND C.name = '" + val + "'";
        }
        if (drpreturnstatus.SelectedIndex > 0)
        {
            string val = objda.validate_search_parameter(drpreturnstatus.SelectedItem.Text);
            condition += " AND A.return_status = '" + val.ToLower() + "'";
        }

        if (drpinvoicenumber.SelectedIndex > 0)
        {
            string val = objda.validate_search_parameter(drpinvoicenumber.SelectedItem.Value);
            condition += " AND A.nid = '" + val.ToLower() + "'";
        }

        if (!string.IsNullOrEmpty(txtfromdate.Text))
        {
            condition += " AND CONVERT(DATE, A.assign_date) >= CONVERT(DATE, '" +
                         objda.validate_search_parameter(txtfromdate.Text) + "')";
        }

        if (!string.IsNullOrEmpty(txttodate.Text))
        {
            condition += " AND CONVERT(DATE, A.assign_date) <= CONVERT(DATE, '" +
                         objda.validate_search_parameter(txttodate.Text) + "')";
        }

        sql += condition;
        sql += " ORDER BY A.nid DESC";

        return sql;
    }


    public void getpageindex(int count)
    {
        if (count <= grvAssign.PageIndex * grvAssign.PageSize)
        {
            grvAssign.PageIndex = 0;
        }

    }
    protected void btnResellerRefresh_Click(object sender, EventArgs e)
    {
        fillDropdowns();
        if (Session["popouaddstatus"] != null && Session["popouaddstatus"].ToString() == "add" && drpReseller.Items.Count > 1)
        {
            drpReseller.SelectedIndex = 1;
            Session["popouaddstatus"] = null;
        }

    }

    public void fillmaster()
    {
        fillDropdowns();
        fillReseller();
        fillroom();
        fillinvoicenumber();
    }
    private void fillinvoicenumber()
    {
        ds = objda.getdata("\r\nSELECT nid, invoice_number \r\nFROM tblProductAssignMaster\r\nWHERE invoice_number IS NOT NULL\r\nAND LTRIM(RTRIM(invoice_number)) <> '';");
        drpinvoicenumber.DataSource = ds;
        drpinvoicenumber.DataTextField = "invoice_number";
        drpinvoicenumber.DataValueField = "nid";
        drpinvoicenumber.DataBind();
        drpinvoicenumber.Items.Insert(0, new System.Web.UI.WebControls.ListItem("Select Invoice Number", ""));
    }


    private void fillReseller()
    {
        ds = objda.getdata("SELECT nid, Name AS Reseller_Name FROM tblResellerMaster WHERE bstatus = 1  AND (active_status='ACTIVE' OR active_status IS NULL)");
        drpname.DataSource = ds;
        drpname.DataTextField = "reseller_name";
        drpname.DataValueField = "nid";
        drpname.DataBind();
        drpname.Items.Insert(0, new System.Web.UI.WebControls.ListItem("Select Reseller", ""));
    }
    private void fillDropdowns()
    {
        ds = objda.getdata("SELECT nid, Name AS Reseller_Name FROM tblResellerMaster WHERE  bstatus = 1  AND (active_status='ACTIVE' OR active_status IS NULL) order by nid desc");
        drpReseller.DataSource = ds;
        drpReseller.DataTextField = "reseller_name";
        drpReseller.DataValueField = "nid";
        drpReseller.DataBind();
        drpReseller.Items.Insert(0, new System.Web.UI.WebControls.ListItem("Select Reseller", ""));
    }
    protected void drpReseller_selectclick(object sender, EventArgs e)
    {
        fillResellerlocation(drpReseller.SelectedItem.Value);
    }
    private void fillResellerlocation(string resellerid)
    {
        ds = objda.getdata("select B.nid,B.locationname from tblResellerlocationmapping as A JOIN tblresellerlocationMaster AS B ON A.Locationid=B.nid WHERE Resellerid='" + resellerid + "'");
        drpresellerlocation.DataSource = ds;
        drpresellerlocation.DataTextField = "locationname";
        drpresellerlocation.DataValueField = "nid";
        drpresellerlocation.DataBind();
        drpresellerlocation.Items.Insert(0, new System.Web.UI.WebControls.ListItem("Select Reseller Location", ""));
    }


    //protected void ckbox_click(object sender, EventArgs e)
    //{
    //    System.Web.UI.WebControls.CheckBox ck_box = (System.Web.UI.WebControls.CheckBox)sender;
    //    GridViewRow row = (GridViewRow)ck_box.NamingContainer;
    //    HiddenField hdnNid = (HiddenField)row.FindControl("hd_nid");
    //    TextBox txtprice = (TextBox)row.FindControl("txtprice");
    //    TextBox txtpercent = (TextBox)row.FindControl("txtpercent");
    //    if (ck_box.Checked == true)
    //    {
    //        ViewState["ck_box"] = "true";
    //        string nid = hdnNid.Value;
    //        txtprice.ReadOnly = true;
    //        txtpercent.ReadOnly = true;
    //        ds = objda.getdata("SELECT * FROM tblproduct_master as A WHERE A.nid = '" + nid + "'");
    //        if (ds.Tables[0].Rows.Count > 0)
    //        {

    //            txtprice.Text = ds.Tables[0].Rows[0]["selling_price"].ToString();
    //            txtpercent.Text = ds.Tables[0].Rows[0]["selling_percent"].ToString();
    //        }
    //    }
    //    else
    //    {
    //        txtpercent.ReadOnly = false;
    //        ViewState["ck_box"] = "false";
    //        txtprice.Text = "0";
    //        txtpercent.Text = "0";
    //    }


    //    CalculateTotals();


    //}

    //protected void txtpercent_TextChanged(object sender, EventArgs e)
    //{
    //    TextBox txtPercent = (TextBox)sender;
    //    GridViewRow row = (GridViewRow)txtPercent.NamingContainer;

    //    Label labP_Price = (Label)row.FindControl("labP_Price");
    //    TextBox txtPrice = (TextBox)row.FindControl("txtprice");

    //    decimal purchasePrice;
    //    decimal percent;

    //    if (labP_Price != null && Decimal.TryParse(labP_Price.Text.Replace("PP:", "").Trim(), out purchasePrice) &&
    //        Decimal.TryParse(txtPercent.Text.Trim(), out percent))
    //    {
    //        decimal sellingPrice = purchasePrice + (purchasePrice * percent / 100);

    //        if (txtPrice != null)
    //        {
    //            txtPrice.Text = sellingPrice.ToString("F2");
    //        }
    //    }

    //    CalculateTotals();
    //}

    protected void btnAddNew_Click(object sender, EventArgs e)
    {
        btnAddNew.Visible = false;
        btnSave.Visible = true;
        drpReseller.Enabled = true;
        txtDate.ReadOnly = false;
        mview.ActiveViewIndex = 1;
        bindproduct();
    }


    protected void btnSave_Click(object sender, EventArgs e)
    {
        try
        {
            if (drpReseller.SelectedItem.Value == "")
            {
                ClientScript.RegisterStartupScript(this.GetType(), "alert", "alert('Please Select Reseller ');", true);
                return;
            }
            savedatatable();

            DataTable dt = (DataTable)ViewState["product_table"];
            if (dt == null || dt.Rows.Count == 0)
            {
                ClientScript.RegisterStartupScript(this.GetType(), "alert", "alert('No rows to save');", true);
                return;
            }
            if (ViewState["editnid"] != null)
            {
                ViewState["new_master_id"] = ViewState["editnid"].ToString();
                objda.action = "update_assign_master_edit";
                objda.id = ViewState["editnid"].ToString();
                objda.image1 = drpReseller.SelectedValue;
                objda.col4 = drpresellerlocation.SelectedValue;
                objda.image2 = txtDate.Text;
                objda.image3 = txttotprice.Text;
                objda.image4 = txttotqauntity.Text;
                objda.col1 = drproomnumber.SelectedValue;
                ds = objda.product_assign_management();
            }
            else
            {

                objda.action = "insert_master";
                objda.image1 = drpReseller.SelectedValue;
                objda.image2 = txtDate.Text;
                objda.col4 = drpresellerlocation.SelectedValue;
                objda.image3 = txttotprice.Text;
                objda.image4 = txttotqauntity.Text;
                objda.col1 = drproomnumber.SelectedValue;
                ds = objda.product_assign_management();
                if (ds.Tables[0].Rows.Count > 0)
                {
                    ViewState["new_master_id"] = ds.Tables[0].Rows[0]["new_id"].ToString();
                }
            }
            fillroom();

            foreach (DataRow row in dt.Rows)
            {


                if (row["assign_id"].ToString() != "0")
                {
                    if (ViewState["editnid"] != null)
                    {
                        objda.id = row["assign_id"].ToString();
                        objda.action = "update";

                    }

                }
                else
                {
                    objda.id = ViewState["new_master_id"].ToString();
                    objda.action = "insert";
                }
                objda.code = row["catid"].ToString();
                objda.ums = row["subcatid"].ToString();
                objda.name = row["productid"].ToString();

                objda.tax2 = row["price"].ToString();
                decimal qty = Convert.ToDecimal(row["quantity"]);
                bool isBarcodeCounted = ViewState["countbarcode"] != null;
                if (isBarcodeCounted)
                {
                    decimal oldqty = Convert.ToDecimal(ViewState["countbarcode"].ToString());
                    if (ViewState["editnid"] != null && oldqty > qty)
                    {
                        qty = qty - oldqty;
                        ViewState["countbarcode"] = null;
                    }

                }


                objda.quantity = qty.ToString(CultureInfo.InvariantCulture);



                objda.col1 = "Approved";


                ds = objda.product_assign_management();
                if (ds.Tables.Count > 0 && ds.Tables[0].Rows.Count > 0)
                {
                    ViewState["newassignid"] = ds.Tables[0].Rows[0]["new_assignid"].ToString();

                }

                DataTable dtbarcode = (DataTable)ViewState["barcode_table"];
                checkbarcode_reserved(dtbarcode);
                DataView dv = new DataView(dtbarcode);

                string catid = row["catid"].ToString();
                string subcatid = row["subcatid"].ToString();
                string productid = row["productid"].ToString();
                dv.RowFilter = "catid = '" + catid + "' AND subcatid = '" + subcatid + "' AND productid = '" + productid + "'";
                List<string> barcodeList = new List<string>();

                if (row["assign_id"].ToString() != "0")
                {
                    DataSet dss = new DataSet();
                    objda.action = "update_assignbarcode";
                    objda.quantity = drpReseller.SelectedValue;
                    objda.status = row["assign_id"].ToString();

                    dss = objda.product_assign_management();

                }

                for (int i = 0; i < dv.Count; i++)
                {
                    if (row["assign_id"].ToString() != "0")
                    {


                        DataSet dss = new DataSet();
                        DataRowView drv = dv[i];
                        objda.action = "updatebarcode_assign";
                        objda.quantity = drpReseller.SelectedValue;
                        objda.status = row["assign_id"].ToString();
                        objda.id = drv["barcodenid"].ToString();
                        dss = objda.product_assign_management();


                        barcodeList.Add(drv["barcodenid"].ToString());

                        objda.action = "insert_product_barcode_logs_m";
                        objda.id = drv["barcodenid"].ToString();
                        objda.status = row["assign_id"].ToString();
                        objda.tax1 = "assign";
                        ds = objda.product_assign_management();
                    }
                    else if (ViewState["newassignid"] != null)
                    {
                        DataSet dss = new DataSet();
                        DataRowView drv = dv[i];
                        objda.action = "updatebarcode_assign";
                        objda.quantity = drpReseller.SelectedValue;
                        objda.status = ViewState["newassignid"].ToString();
                        objda.id = drv["barcodenid"].ToString();
                        dss = objda.product_assign_management();


                        barcodeList.Add(drv["barcodenid"].ToString());

                        objda.action = "insert_product_barcode_logs_m";
                        objda.id = drv["barcodenid"].ToString();
                        objda.status = ViewState["newassignid"].ToString();
                        objda.tax1 = "assign";
                        ds = objda.product_assign_management();


                        //objda.action = "insert_barcode";
                        //objda.code = drv["barcodenid"].ToString();
                        //objda.id2 = ViewState["newassignid"].ToString();
                        //objda.type = "assign";
                        //ds = objda.sp_resellerbarcodelogs();

                    }

                }

                string barcodenids = string.Join(",", barcodeList);
            }
            btnlnksink_Click();
            ClientScript.RegisterStartupScript(this.GetType(), "alert", "alert('Assignment saved successfully');", true);
            bindgrid();
            clearform();
            mview.ActiveViewIndex = 0;
        }
        catch (Exception ex)
        {
            ClientScript.RegisterStartupScript(this.GetType(), "alert", "alert('Invalid');", true);
        }
    }
    public void btnlnksink_Click()
    {

        string message = oSyncdata.syncrficapi();

        ClientScript.RegisterStartupScript(this.GetType(), "alert",
            "alert('" + message + "');", true);
        return;
    }


    public void checkbarcode_reserved(DataTable dt)
    {
        if (dt.Rows.Count > 0)
        {
            foreach (DataRow dr in dt.Rows)
            {
                objda.action = "check_barcode_reserve";
                objda.id = dr["barcodenid"].ToString();
                objda.name = drpReseller.SelectedItem.Value;
                ds = objda.product_assign_management();
            }
        }
    }
    protected void DisableGridViewControls(GridView grid)
    {
        foreach (GridViewRow row in grid.Rows)
        {
            foreach (System.Web.UI.Control ctrl in row.Controls)
            {
                DisableChildControls(ctrl); // Disable all inner controls
            }
        }
    }

    private void DisableChildControls(System.Web.UI.Control parent)
    {
        foreach (System.Web.UI.Control child in parent.Controls)
        {
            // Classic syntax for C# 4.0 (no pattern matching)
            if (child is WebControl)
            {
                ((WebControl)child).Enabled = false;
            }

            // If control has children, go deeper recursively
            if (child.HasControls())
            {
                DisableChildControls(child);
            }
        }
    }

    protected void grvAssign_RowCommand(object sender, GridViewCommandEventArgs e)
    {
        fillmaster();
        objda.id = e.CommandArgument.ToString();


        if (e.CommandName == "editrec")
        {
            objda.action = "select_single";
            GridViewRow row = (GridViewRow)((System.Web.UI.Control)e.CommandSource).NamingContainer;
            LinkButton txtReturn = (LinkButton)row.FindControl("txt_return");
            HiddenField hidreturn_status = (HiddenField)row.FindControl("hidreturn_status");

            DataSet ds = objda.product_assign_management();

            if (ds.Tables[0].Rows.Count > 0)
            {

                ViewState["editnid"] = ds.Tables[0].Rows[0]["master_id"].ToString();
                drpReseller.SelectedValue = ds.Tables[0].Rows[0]["Reseller_ID"].ToString();
                txtDate.Text = ds.Tables[0].Rows[0]["p_assign_date"].ToString();

                txttotqauntity.Text = ds.Tables[0].Rows[0]["total_quantity"].ToString();

                Decimal totalPrice = Convert.ToDecimal(ds.Tables[0].Rows[0]["total_price"]);
                txttotprice.Text = totalPrice.ToString("F4");
                drpReseller.Enabled = true;
                txtDate.ReadOnly = false;

                //ViewState["old_table_index"] = ds.Tables[0].Rows[0]["nid"].ToString();
                //for (int i = 0, j = 0; ds.Tables[0].Rows.Count > i; i++)
                //{
                //    j++;
                //    ViewState["old_table_index"] = j;
                //}

                //DataTable dt = new DataTable();
                //DataColumn dc = new DataColumn("catid", typeof(string));
                //dt.Columns.Add(dc);
                //dc = new DataColumn("subcatid", typeof(string));
                //dt.Columns.Add(dc);
                //dc = new DataColumn("productid", typeof(string));
                //dt.Columns.Add(dc);
                //dc = new DataColumn("barcodenid", typeof(string));
                //dt.Columns.Add(dc);
                //dc = new DataColumn("rowid", typeof(string));
                //dt.Columns.Add(dc);
                //ViewState["barcode_table"] = dt;


                DataTable barcode_table = new DataTable();
                barcode_table.Columns.Add("catid");
                barcode_table.Columns.Add("subcatid");
                barcode_table.Columns.Add("productid");
                barcode_table.Columns.Add("barcodenid");
                barcode_table.Columns.Add("rowid");

                DataTable dt = new DataTable();
                dt.Columns.Add("rowid");
                dt.Columns.Add("nid");
                dt.Columns.Add("assign_id");
                dt.Columns.Add("catid");
                dt.Columns.Add("subcatid");
                dt.Columns.Add("ckbox_pro");
                dt.Columns.Add("productid");
                dt.Columns.Add("hidnid");
                dt.Columns.Add("labqty_product");
                dt.Columns.Add("txt_product_qty");
                dt.Columns.Add("txt_safe_qty");
                dt.Columns.Add("price");
                dt.Columns.Add("totalprice");
                dt.Columns.Add("quantity");
                int rowid = 1;
                int rowCounter = 1;
                decimal sellingPrice = 0;
                int quantity = 0;
                foreach (DataRow dr in ds.Tables[0].Rows)
                {
                    DataRow newRow = dt.NewRow();
                    newRow["rowid"] = rowCounter++;
                    newRow["nid"] = dr["nid"].ToString();
                    newRow["assign_id"] = dr["assign_id"].ToString();
                    newRow["catid"] = dr["category"].ToString();
                    newRow["subcatid"] = dr["sub_category"].ToString();
                    newRow["productid"] = dr["Product_Id"].ToString();
                    newRow["ckbox_pro"] = dr["price_check"].ToString();
                    decimal.TryParse(dr["selling_price"].ToString(), out sellingPrice);
                    int.TryParse(dr["quantity"].ToString(), out quantity);

                    newRow["totalprice"] = (sellingPrice * quantity).ToString("0.00");
                    newRow["labqty_product"] = "P.Q - " + dr["current_quantity"].ToString() +
                               " , SH.Q - " + dr["safehouse_quantity"].ToString() +
                               " , C.Q - " + dr["company_stock"].ToString();


                    newRow["txt_product_qty"] = "Stock -> " + dr["current_quantity"].ToString();
                    newRow["txt_safe_qty"] = "S.House Stock -> " + dr["safehouse_quantity"].ToString();
                    newRow["price"] = dr["selling_price"].ToString();
                    newRow["quantity"] = dr["quantity"].ToString();
                    newRow["hidnid"] = dr["nid"].ToString();
                    dt.Rows.Add(newRow);


                    objda.action = "select_barcode_assignid";
                    objda.id = dr["assign_id"].ToString();
                    DataSet dss = objda.product_assign_management();

                    //string barcodes = dr["barcode_nid"].ToString(); // Example: "85,89,103"
                    //List<System.Web.UI.WebControls.ListItem> barcodeItems = new List<System.Web.UI.WebControls.ListItem>();

                    if (dss.Tables[0].Rows.Count > 0)
                    {
                        //string[] barcodeArray = barcodes.Split(',');
                        foreach (DataRow subdr in dss.Tables[0].Rows)
                        {

                            DataRow newbarcodeRow = barcode_table.NewRow();
                            newbarcodeRow["catid"] = dr["category"].ToString();
                            newbarcodeRow["subcatid"] = dr["sub_category"].ToString();
                            newbarcodeRow["productid"] = dr["Product_Id"].ToString();
                            newbarcodeRow["barcodenid"] = subdr["nid"].ToString();
                            newbarcodeRow["rowid"] = rowid;
                            barcode_table.Rows.Add(newbarcodeRow);
                        }
                        rowid++;
                    }


                }

                ViewState["barcode_table"] = barcode_table;
                ViewState["product_table"] = dt;

                grview.DataSource = dt;
                grview.DataBind();
                btnSave.Visible = true;
                if (hidreturn_status.Value.ToLower() == "complete")
                {
                    DisableGridViewControls(grview);
                    btnSave.Visible = false;
                }
                mview.ActiveViewIndex = 1;
            }
        }
        else if (e.CommandName == "return")
        {
            string master_id = e.CommandArgument.ToString();
            GridViewRow row = (GridViewRow)((System.Web.UI.Control)e.CommandSource).NamingContainer;
            LinkButton txtReturn = (LinkButton)row.FindControl("txt_return");
            HiddenField hidreturn_status = (HiddenField)row.FindControl("hidreturn_status");
            string url = "ProductReturn.aspx?master_id=" + master_id + "&txtReturn=" + hidreturn_status.Value;
            Response.Redirect(url);
        }


        else if (e.CommandName == "viewinvoice")
        {
            string fileName = e.CommandArgument.ToString();
            string relativePath = "~/iadmin/documents/invoice/" + fileName;
            string filePath = Server.MapPath(relativePath);

            if (File.Exists(filePath))
            {
                string url = ResolveUrl(relativePath);


                string script = "open_master('" + url.Replace("'", "\\'") + "');";
                ScriptManager.RegisterStartupScript(this, this.GetType(), "OpenInvoicePopup", script, true);
            }
            else
            {
                ScriptManager.RegisterStartupScript(this, this.GetType(), "AlertInvoice", "alert('Invoice not found.');", true);
            }
        }

        else if (e.CommandName == "invoice_cancel")
        {
            int rowIndex = ((GridViewRow)((System.Web.UI.Control)e.CommandSource).NamingContainer).RowIndex;

            HiddenField hidreturn_status = (HiddenField)grvAssign.Rows[rowIndex].FindControl("hidreturn_status");
            HiddenField hdassignmaster_id = (HiddenField)grvAssign.Rows[rowIndex].FindControl("hdassignmaster_id");

            ViewState["assignmaster_id"] = hdassignmaster_id.Value;


            if (string.IsNullOrEmpty(hidreturn_status.Value) || hidreturn_status.Value.ToLower() != "complete")
            {
                ScriptManager.RegisterStartupScript(this, GetType(), "AlertInvoice", "alert('Return is not complete.');", true);
                return;
            }


            objda.action = "get_assign_metalrate";
            objda.id = hdassignmaster_id.Value;
            DataSet ds = objda.product_assign_management();

            if (ds.Tables.Count > 0 && ds.Tables[0].Rows.Count > 0)
            {
                decimal paidAmount = 0;

                if (ds.Tables[0].Columns.Contains("paidamount"))
                {
                    decimal.TryParse(ds.Tables[0].Rows[0]["paidamount"].ToString(), out paidAmount);
                }

                if (paidAmount > 0)
                {
                    ScriptManager.RegisterStartupScript(this, GetType(), "AlertInvoice",
                        "alert('Paid amount is greater than zero, so invoice cannot be cancelled.');", true);
                    return;
                }
            }


            objda.action = "insert_invoice_log";
            objda.masterid = hdassignmaster_id.Value;
            DataSet dsLog = objda.sp_invoicecancel_mgmt();

            if (dsLog.Tables.Count > 0 && dsLog.Tables[0].Rows.Count > 0)
            {
                string newid = dsLog.Tables[0].Rows[0]["newcancelid"].ToString();

                foreach (DataRow dr in dsLog.Tables[0].Rows)
                {
                    objda.action = "insert_invoice_baselog";
                    objda.id2 = newid;
                    objda.assesmentyear = dr["nid"].ToString();
                    objda.code = dr["barcode_number"].ToString();

                    DataSet dsInner = objda.sp_invoicecancel_mgmt();
                }
            }

            ScriptManager.RegisterStartupScript(this, GetType(), "AlertInvoice", "alert('Invoice cancellation request applied successfully.');", true);
        }
        else if (e.CommandName == "Payment_invoice")
        {


            int rowIndex = ((GridViewRow)((System.Web.UI.Control)e.CommandSource).NamingContainer).RowIndex;
            int nid2 = Convert.ToInt32(e.CommandArgument);
            ViewState["rateid2"] = nid2;

            LinkButton txtReturn = (LinkButton)grvAssign.Rows[rowIndex].FindControl("txt_return");
            HiddenField hidreturn_status = (HiddenField)grvAssign.Rows[rowIndex].FindControl("hidreturn_status");
            HiddenField hndassignpaymnet = (HiddenField)grvAssign.Rows[rowIndex].FindControl("hndassignpaymnet");
            HiddenField hdassignmaster_id = (HiddenField)grvAssign.Rows[rowIndex].FindControl("hdassignmaster_id");
            ViewState["assignmaster_id"] = hdassignmaster_id.Value;



            if (hidreturn_status.Value.ToLower() != "complete")
            {
                ScriptManager.RegisterStartupScript(this, GetType(), "AlertInvoice", "alert('Return is not complete .');", true);
                return;
            }

            DataSet dsalivndicount = objda.getdata("select * from tblProductAssignMaster where nid='" + ViewState["assignmaster_id"].ToString() + "'");
            if (dsalivndicount.Tables[0].Rows.Count > 0 &&
                dsalivndicount.Tables[0].Rows[0]["alvin_discount_status"].ToString() == "apply")
            {
                ScriptManager.RegisterStartupScript(this, GetType(), "AlreadyPending",
                    "alert('Discount already pending admin approval. You cannot apply again.');", true);
                return;
            }

            string paymentStatus = hndassignpaymnet.Value.Trim().ToLower();
            if (paymentStatus == "complete" || paymentStatus == "partial")
            {
                string folderPath = Server.MapPath("~/iadmin/documents/invoice/");
                string fileName = "invoice_pdf_00" + ViewState["rateid2"] + ".pdf";
                string filePath = Path.Combine(folderPath, fileName);

                if (File.Exists(filePath))
                {
                    string relativePath = ResolveUrl("~/iadmin/documents/invoice/" + fileName);
                    string script =
                        "alert('Payment has already been received for this invoice. Showing the last generated invoice.');" +
                        "window.open('" + relativePath + "', '_blank');";

                    ScriptManager.RegisterStartupScript(this, this.GetType(), "PaymentExistsAndOpen", script, true);
                }
                else
                {
                    ScriptManager.RegisterStartupScript(this, this.GetType(), "alertMessage",
                        "alert('Payment has already been received for this invoice, but the invoice file could not be found.');", true);
                }
                return;
            }




            DataSet dsinvoice = objda.getdata("select a.nid,b.alvin_discount_status,a.invoice_url from tbladmindiscountmaster  as A join  tblProductAssignMaster as B ON A.assign_masterid =B.nid" +
                " where b.nid='" + ViewState["assignmaster_id"].ToString() + "' and b.alvin_discount_status='approve' and a.bstatus=1");
            if (dsinvoice.Tables[0].Rows.Count > 0 &&
                dsinvoice.Tables[0].Rows[0]["alvin_discount_status"].ToString() == "approve")
            {
                string url = dsinvoice.Tables[0].Rows[0]["invoice_url"].ToString();

                string script = "window.open('" + url + "', '_blank');";
                ClientScript.RegisterStartupScript(this.GetType(), "OpenWindow", script, true);

                return;
            }

            int nid = Convert.ToInt32(e.CommandArgument);
            ViewState["rateid"] = nid;
            string sql = generatequeryrate("");
            ds = new DataSet();
            ds = objda.getdata(sql);
            if (ds.Tables[0].Rows.Count > 0)
            {

                GridView2.Visible = true;
                GridView2.DataSource = ds;
                GridView2.DataBind();

            }
            else
            {

                GridView2.Visible = false;
            }

            objda.action = "get_assign_metalrate";
            objda.id = nid.ToString();
            DataSet dsmetal = objda.product_assign_management();
            if (dsmetal.Tables.Count > 0 && dsmetal.Tables[0].Rows.Count > 0)
            {
                LinkButton5.Visible = true;
                legendmetal.Visible = true;
                grmetalrate.DataSource = dsmetal;
                grmetalrate.DataBind();

            }
            else
            {
                LinkButton5.Visible = false;
                legendmetal.Visible = false;
                grmetalrate.DataSource = null;
                grmetalrate.DataBind();
            }

            divpaymnet.Visible = true;
            divbarcode.Visible = false;
            ClientScript.RegisterStartupScript(typeof(Page), "temp", "<script type='text/javascript'>openbarcodepopup();</script>");



        }

    }

    public string generatequeryrate(string type)
    {
        string str = "";

        str += "select B.NID,B.name,B.code,A.converter_rate from tblcurrency_converter as A JOIN tblgeneric_data AS B ON A.currency_id = B.nid WHERE B.bstatus = 1  and b.value_type = 'Currency'  order by A.creationdate desc ";


        return str;
    }
    protected string GetConvertedAmount(object totalPrice)
    {
        if (totalPrice == DBNull.Value || ViewState["rate"] == null)
            return "PHP 0.00";

        double price = Convert.ToDouble(totalPrice);
        double rate = Convert.ToDouble(ViewState["rate"]);

        return "PHP " + (price * rate).ToString("N2");
    }

    protected void GridView2_RowCommand(object sender, GridViewCommandEventArgs e)
    {

        if (e.CommandName == "EditItem")
        {
            // Get row
            GridViewRow row =
                ((Button)e.CommandSource).NamingContainer as GridViewRow;

            // Get ID
            int nid = Convert.ToInt32(e.CommandArgument);

            // Get New Rate textbox
            TextBox txtNewRate =
                row.FindControl("txtNewRate") as TextBox;

            if (txtNewRate == null || string.IsNullOrWhiteSpace(txtNewRate.Text))
            {
                ClientScript.RegisterStartupScript(
                    GetType(), "alert",
                    "alert('Please enter new rate');", true);
                return;
            }
            string assignmasterid = ViewState["assignmaster_id"].ToString();
            // Save
            objda.id = assignmasterid.ToString();
            objda.action = "get_data_chanegrate";
            objda.name = nid.ToString();
            ds = objda.product_master_management();
            if (ds.Tables[0].Rows.Count > 0)
            {
                foreach (DataRow dr in ds.Tables[0].Rows.Cast<DataRow>().ToList())
                {
                    objda.id = dr["nid"].ToString();
                    objda.action = "update_data_chanegrate";
                    objda.name = txtNewRate.Text.ToString();
                    objda.catid = "apply";

                    objda.product_master_management();
                }
            }



            divpaymnet.Visible = true;
            divbarcode.Visible = false;
            ViewState["editdata"] = "true";
            // Show success alert and call JS function to open popup
            ClientScript.RegisterStartupScript(
                typeof(Page),
                "temp",
                "<script type='text/javascript'>alert('Converter Rate Saved Successfully'); openbarcodepopup();</script>");
        }
    }

    protected void GridView3_RowCommand(object sender, GridViewCommandEventArgs e)
    {
        if (e.CommandName != "EditItem") return;

        GridViewRow row = ((Button)e.CommandSource).NamingContainer as GridViewRow;

        TextBox txtNewRate = row.FindControl("txtNewRate") as TextBox;
        HiddenField hndpurity_id = row.FindControl("hndpurity_id") as HiddenField;

        if (txtNewRate == null || string.IsNullOrWhiteSpace(txtNewRate.Text))
        {
            ClientScript.RegisterStartupScript(
                GetType(), "alert",
                "alert('Please enter new rate');", true);
            return;
        }

        objda.id = hndpurity_id.Value;
        objda.action = "";
        objda.id2 = ViewState["assignmaster_id"].ToString();
        objda.rate = txtNewRate.Text;
        ds = objda.sp_metalrate_mgmt();


        bool isJewelleryMetal = ds != null
            && ds.Tables.Count > 0
            && ds.Tables[0].Rows.Count > 0
            && ds.Tables[0].Columns.Contains("Jewellery_Metal")
            && ds.Tables[0].Rows[0]["Jewellery_Metal"].ToString() == "jewellerymetal";

        if (isJewelleryMetal)
        {
            ViewState["Jewellery_Metal"] = "yes";
        }

        ViewState["editdata"] = "true";
        divpaymnet.Visible = true;
        divbarcode.Visible = false;

        ClientScript.RegisterStartupScript(
            typeof(Page),
            "temp",
            "<script type='text/javascript'>alert('Metal Rate Saved Successfully'); openbarcodepopup();</script>");
    }

    protected void btnapplyalvindiscount_click(object sender, EventArgs e)
    {
        objda.action = "insert_alvin_discount";
        if (ViewState["assignmaster_id"] == null)
        {
            return;
        }

        string url = "ResellerPaymentInvoice.aspx?pdf=1&id="
               + ViewState["rateid"].ToString();
        objda.type = "false";
        if (ViewState["editdata"] != null && ViewState["editdata"].ToString() == "true")
        {
            url = "ResellerPaymentInvoice.aspx?id="
                     + ViewState["rateid"].ToString()
                     + "&edit=1&pdf=1";
            objda.type = "true";
        }
        objda.name2 = url;
        objda.id = ViewState["assignmaster_id"].ToString();
        objda.name = txtalvindiscount.Text;
        ds = objda.product_assign_management();


        if (ViewState["Jewellery_Metal"] != null)
        {

            objda.action = "Metal_Jewellery_Update";
            objda.id2 = ViewState["assignmaster_id"].ToString();

            ds = objda.sp_metalrate_mgmt();
        }
        string script = "alert('Please approve this discount to admin.');";
        script += "if (window.opener && !window.closed) { window.close(); }";
        ClientScript.RegisterStartupScript(this.GetType(), "DiscountApplied", script, true);
    }

    protected void btnsubmitrate_ClickNEW(object sender, EventArgs e)
    {

        if (ViewState["Jewellery_Metal"] != null)
        {

            objda.action = "Metal_Jewellery_Update";
            objda.id2 = ViewState["assignmaster_id"].ToString();

            ds = objda.sp_metalrate_mgmt();
        }

        LinkButton3.Visible = false;
        LinkButton1.Visible = true;
        LinkButton5.Visible = true;

        if (ViewState["first"] == null && ViewState["first2"] == null)
        {
            ViewState["first2"] = "1";
            ViewState["first"] = "1";
            divpaymnet.Visible = true;
            divbarcode.Visible = false;
            ClientScript.RegisterStartupScript(
                typeof(Page),
                "openPopup",
                "<script type='text/javascript'>openbarcodepopup();</script>");
            return;
        }



        if (ViewState["rateid"] != null)
        {
            string url = "ResellerPaymentInvoice.aspx?id="
                       + ViewState["rateid"].ToString()
                       + "&edit=1&pdf=1";


            divpaymnet.Visible = false;
            divbarcode.Visible = false;

            ScriptManager.RegisterStartupScript(
                this, GetType(),
                "CloseAndOpen",
                "closePopupAndOpen('" + url + "');",
                true);
        }
        ViewState["first2"] = null;
        ViewState["first"] = null;
    }
    //protected void GridView3_RowCommand(object sender, GridViewCommandEventArgs e)
    //{
    //    if (e.CommandName == "EditItem")
    //    {
    //        // Get row
    //        GridViewRow row =
    //            ((Button)e.CommandSource).NamingContainer as GridViewRow;

    //        // Get ID
    //        int nid = Convert.ToInt32(e.CommandArgument);

    //        // Get New Rate textbox
    //        TextBox txtNewRate = row.FindControl("txtNewRate") as TextBox;
    //        HiddenField hndpurity_id = row.FindControl("hndpurity_id") as HiddenField;


    //        if (txtNewRate == null || string.IsNullOrWhiteSpace(txtNewRate.Text))
    //        {
    //            ClientScript.RegisterStartupScript(
    //                GetType(), "alert",
    //                "alert('Please enter new rate');", true);
    //            return;
    //        }

    //        // Save
    //        objda.id = hndpurity_id.Value.ToString();
    //        objda.action = "";
    //        objda.id2 = ViewState["assignmaster_id"].ToString();
    //        objda.rate = txtNewRate.Text;
    //        ds = objda.sp_metalrate_mgmt();

    //        if (ds.Tables.Count > 0 && ds.Tables[0].Rows[0]["Jewellery_Metal"].ToString() == "jewellerymetal")
    //        {
    //            ViewState["Jewellery_Metal"] = "yes";


    //        }
    //        objda.id = hndpurity_id.Value.ToString();
    //        objda.action = "Metal_Jewellery_Update";
    //        objda.id2 = ViewState["assignmaster_id"].ToString();
    //        objda.rate = txtNewRate.Text;
    //        ds = objda.sp_metalrate_mgmt();

    //        divpaymnet.Visible = true;
    //        divbarcode.Visible = false;

    //        // Show success alert and call JS function to open popup
    //        ClientScript.RegisterStartupScript(
    //            typeof(Page),
    //            "temp",
    //            "<script type='text/javascript'>alert('Metal Rate Saved Successfully'); openbarcodepopup();</script>");
    //    }
    //}


    //protected void btnsubmitrate_ClickNEW(object sender, EventArgs e)
    //{
    //    if (ViewState["Jewellery_Metal"] != null && ViewState["Jewellery_Metal"].ToString() = "yes")
    //    {
    //        // objda.id = hndpurity_id.Value.ToString();
    //        objda.action = "Metal_Jewellery_Update";
    //        objda.id2 = ViewState["assignmaster_id"].ToString();
    //        //    objda.rate = txtNewRate.Text;
    //        ds = objda.sp_metalrate_mgmt();
    //    }

    //    // Enable Grid editing
    //    LinkButton3.Visible = false;
    //    LinkButton1.Visible = true;

    //    // FIRST click → open popup
    //    if (ViewState["first"] == null)
    //    {
    //        ViewState["first"] = "1";

    //        divpaymnet.Visible = true;
    //        divbarcode.Visible = false;

    //        ClientScript.RegisterStartupScript(
    //            typeof(Page),
    //            "openPopup",
    //            "<script type='text/javascript'>openbarcodepopup();</script>"
    //        );
    //        return;
    //    }

    //    // SECOND click → close popup then open invoice
    //    if (ViewState["rateid"] != null)
    //    {
    //        string url = "ResellerPaymentInvoice.aspx?id="
    //        + ViewState["rateid"].ToString()
    //        + "&edit=1&pdf=1";



    //        divpaymnet.Visible = false;
    //        divbarcode.Visible = false;

    //        ScriptManager.RegisterStartupScript(
    //            this,
    //            GetType(),
    //            "CloseAndOpen",
    //            "closePopupAndOpen('" + url + "');",
    //            true
    //        );
    //    }

    //    ViewState["first"] = null;
    //}
    protected void btnoldinvoice_Click(object sender, EventArgs e)
    {

        string folderPath = Server.MapPath("~/iadmin/documents/invoice/");
        string fileName = "invoice_pdf_00" + ViewState["rateid"] + ".pdf";
        string filePath = Path.Combine(folderPath, fileName);

        if (File.Exists(filePath))
        {

            string relativePath = ResolveUrl("~/iadmin/documents/invoice/" + fileName);
            ScriptManager.RegisterStartupScript(this, this.GetType(),
                "openInvoice", "window.open('" + relativePath + "', '_blank');", true);
        }
        else
        {

            ScriptManager.RegisterStartupScript(this, this.GetType(),
                "alertMessage", "alert('Invoice file not found.');", true);
        }
    }




    protected void btncontinuous_Click(object sender, EventArgs e)
    {
        if (ViewState["rateid"] == null)
            return;
        foreach (GridViewRow row in GridView2.Rows)
        {
            if (row.RowType == DataControlRowType.DataRow)
            {
                string nid = GridView2.DataKeys[row.RowIndex].Value.ToString();
                Label lblCode = row.FindControl("lblCode") as Label;
                TextBox txtNewRate = row.FindControl("txtNewRate") as TextBox;
                Label lblConverterRate = row.FindControl("lblConverterRate") as Label;
                if (lblCode != null && txtNewRate == null)
                {
                    objda.id = nid.ToString();
                    objda.action = "update_Converter_rate_edit";
                    objda.name = lblConverterRate.Text;
                    ds = objda.Jewellery_master_mgmt();
                }
            }
        }

        objda.action = "update_ratechange_status";
        objda.id = ViewState["assignmaster_id"].ToString();
        DataSet dsnew = objda.product_master_management();

        string url = "ResellerPaymentInvoice.aspx?pdf=1&id="
            + ViewState["rateid"].ToString();

        ViewState["first2"] = null;
        ViewState["first"] = null;

        divpaymnet.Visible = false;
        divbarcode.Visible = false;


        ScriptManager.RegisterStartupScript(
            this,
            GetType(),
            "CloseAndOpen",
            "closePopupAndOpen('" + url + "');",
            true
        );

    }

    protected void btnsubmitrate_Click(object sender, EventArgs e)
    {

        LinkButton3.Visible = true;
        LinkButton1.Visible = false;

        foreach (GridViewRow row in GridView2.Rows)
        {
            if (row.RowType == DataControlRowType.DataRow)
            {
                Button btnEdit = row.FindControl("btnedit") as Button;
                if (btnEdit != null) btnEdit.Enabled = true;

                TextBox txtRate = row.FindControl("txtNewRate") as TextBox;
                if (txtRate != null) txtRate.ReadOnly = false;
            }
        }


        if (ViewState["first"] == null)
        {
            ViewState["first"] = "1";

            divpaymnet.Visible = true;
            divbarcode.Visible = false;

            ClientScript.RegisterStartupScript(
                typeof(Page),
                "openPopup",
                "<script type='text/javascript'>openbarcodepopup();</script>"
            );
            return;
        }


        if (ViewState["rateid"] != null)
        {
            string url = "ResellerPaymentInvoice.aspx?id="
           + ViewState["rateid"].ToString()
           + "&edit=1&pdf=1";



            divpaymnet.Visible = false;
            divbarcode.Visible = false;

            ScriptManager.RegisterStartupScript(
                this,
                GetType(),
                "CloseAndOpen",
                "closePopupAndOpen('" + url + "');",
                true
            );
        }

        ViewState["first"] = null;

    }



    protected void btnmetalrate_Click(object sender, EventArgs e)
    {

        LinkButton3.Visible = true;
        LinkButton5.Visible = false;

        foreach (GridViewRow row in grmetalrate.Rows)
        {
            if (row.RowType == DataControlRowType.DataRow)
            {
                Button btnEdit = row.FindControl("btnedit") as Button;
                if (btnEdit != null) btnEdit.Enabled = true;

                TextBox txtRate = row.FindControl("txtNewRate") as TextBox;
                if (txtRate != null) txtRate.ReadOnly = false;
            }
        }


        if (ViewState["first2"] == null)
        {
            ViewState["first2"] = "1";

            divpaymnet.Visible = true;
            divbarcode.Visible = false;

            ClientScript.RegisterStartupScript(
                typeof(Page),
                "openPopup",
                "<script type='text/javascript'>openbarcodepopup();</script>"
            );
            return;
        }


        if (ViewState["rateid"] != null)
        {
            string url = "ResellerPaymentInvoice.aspx?id="
           + ViewState["rateid"].ToString()
           + "&edit=1&pdf=1";



            divpaymnet.Visible = false;
            divbarcode.Visible = false;

            ScriptManager.RegisterStartupScript(
                this,
                GetType(),
                "CloseAndOpen",
                "closePopupAndOpen('" + url + "');",
                true
            );
        }

        ViewState["first2"] = null;
    }


    private string GetContentType(string filePath)
    {
        string ext = Path.GetExtension(filePath).ToLower();
        switch (ext)
        {
            case ".jpg":
            case ".jpeg": return "image/jpeg";
            case ".png": return "image/png";
            case ".gif": return "image/gif";
            case ".pdf": return "application/pdf";
            default: return "application/octet-stream";
        }
    }


    private void clearform()
    {

        drpReseller.SelectedIndex = 0;
        ViewState["barcode_table"] = null;
        ViewState["product_table"] = null;
        txtDate.Text = "";
        txttotqauntity.Text = "";
        txttotprice.Text = "";
        ScriptManager.RegisterStartupScript(this, this.GetType(), "clearRows", @"
        setTimeout(function() {
            let tbody = document.getElementById('roughTableBody');
            if (tbody) {
                tbody.innerHTML = '';
                // Optionally add a default row back
                __doPostBack('', '');
            }
        }, 100);", true);
    }



    protected void txtPriceOrQty_TextChanged(object sender, EventArgs e)
    {
        CalculateTotals();
    }
    private void CalculateTotals()
    {
        decimal totalPrice = 0;
        int totalQuantity = 0;
        decimal oldprice = 0;
        foreach (GridViewRow row in grview.Rows)
        {
            HiddenField hdnprice = (HiddenField)row.FindControl("hdnprice");

            TextBox txtQuantity = (TextBox)row.FindControl("txtqauntity");

            decimal price;
            int quantity;

            if (hdnprice.Value != null && Decimal.TryParse(hdnprice.Value, out price))
            {
                oldprice = price;
            }

            if (txtQuantity != null && Int32.TryParse(txtQuantity.Text, out quantity))
            {
                totalQuantity += quantity;
                if (quantity > 0)
                {
                    totalPrice += (oldprice * quantity);
                }
                else
                {
                    totalPrice += 0;
                }
            }
        }

        txttotprice.Text = totalPrice.ToString("F4");

        txttotqauntity.Text = totalQuantity.ToString();
    }


    public void createdatatable()
    {
        DataTable dt = new DataTable();
        DataColumn dc = new DataColumn("catid", typeof(string));
        dt.Columns.Add(dc);
        dc = new DataColumn("subcatid", typeof(string));
        dt.Columns.Add(dc);
        dc = new DataColumn("productid", typeof(string));
        dt.Columns.Add(dc);


        dc = new DataColumn("price", typeof(string));
        dt.Columns.Add(dc);
        dc = new DataColumn("totalprice", typeof(string));
        dt.Columns.Add(dc);
        dc = new DataColumn("quantity", typeof(string));
        dt.Columns.Add(dc);
        dc = new DataColumn("nid", typeof(string));
        dt.Columns.Add(dc);
        dc = new DataColumn("assign_id", typeof(string));
        dt.Columns.Add(dc);
        dc = new DataColumn("rowid", typeof(string));
        dt.Columns.Add(dc);
        dc = new DataColumn("labqty_product", typeof(string));
        dt.Columns.Add(dc);
        dc = new DataColumn("txt_product_qty", typeof(string));
        dt.Columns.Add(dc);
        dc = new DataColumn("txt_safe_qty", typeof(string));
        dt.Columns.Add(dc);
        ViewState["product_table"] = dt;
    }

    public void add_product_row()
    {
        if (ViewState["product_table"] == null)
        {
            createdatatable();
        }
        DataTable dt = (DataTable)ViewState["product_table"];
        int rowid = 0;
        object result = dt.Compute("MAX(rowid)", string.Empty);
        if (result != DBNull.Value)
        {
            rowid = Convert.ToInt32(result);
        }
        rowid++;


        DataRow dr = dt.NewRow();
        dr["catid"] = "0";
        dr["subcatid"] = "0";
        dr["productid"] = "0";

        dr["totalprice"] = "0";
        dr["price"] = "0";
        dr["quantity"] = "0";
        dr["nid"] = "0";
        dr["assign_id"] = "0";

        dr["rowid"] = rowid.ToString();
        dr["txt_product_qty"] = "0";
        dr["labqty_product"] = "0";
        dr["txt_safe_qty"] = "0";
        dt.Rows.Add(dr);
    }

    public void bindproduct()
    {
        if (ViewState["product_table"] == null)
        {
            add_product_row();
        }
        DataTable dt = (DataTable)ViewState["product_table"];
        grview.DataSource = dt;
        grview.DataBind();

    }

    protected void grview_RowCommand(object sender, GridViewCommandEventArgs e)
    {
        if (e.CommandName == "add_product")
        {
            savedatatable();
            add_product_row();
            bindproduct();

        }

        if (e.CommandName == "remove_product")
        {
            int rowIndex = Convert.ToInt32(e.CommandArgument);
            LinkButton lnk = (LinkButton)e.CommandSource;

            // Get the GridViewRow it belongs to
            GridViewRow row = (GridViewRow)lnk.NamingContainer;
            HiddenField hdAssignId = (HiddenField)row.FindControl("hd_assign_id");
            DropDownList drpcategory = (DropDownList)row.FindControl("drpcategory");
            DropDownList ddlSubCategory = (DropDownList)row.FindControl("ddlSubCategory");
            DropDownList drpProduct = (DropDownList)row.FindControl("drpProduct");

            savedatatable();
            remove_product_row(e.CommandArgument.ToString(), hdAssignId.Value);
            bindproduct();
            removebartable(drpcategory.SelectedValue, ddlSubCategory.SelectedValue, drpProduct.SelectedValue);
        }

        CalculateTotals();
    }

    public void remove_product_row(string rowid, string assign_id)
    {
        DataTable dt = (DataTable)ViewState["product_table"];
        foreach (DataRow row in dt.Rows)
        {

            if (row["rowid"].ToString() == rowid)
            {
                objda.action = "remove_assign_product";
                objda.id = assign_id;
                ds = objda.product_assign_management();
                row.Delete();
                break;

            }
        }

    }

    public void savedatatable()
    {

        DataTable dt = (DataTable)ViewState["product_table"];
        for (int i = 0; i < grview.Rows.Count; i++)
        {

            System.Web.UI.WebControls.DropDownList drpcategory = (System.Web.UI.WebControls.DropDownList)grview.Rows[i].FindControl("drpcategory");
            System.Web.UI.WebControls.DropDownList drpsubcat = (System.Web.UI.WebControls.DropDownList)grview.Rows[i].FindControl("ddlSubCategory");
            System.Web.UI.WebControls.DropDownList drpproduct = (System.Web.UI.WebControls.DropDownList)grview.Rows[i].FindControl("drpProduct");
            System.Web.UI.WebControls.TextBox txt_product_qty = (System.Web.UI.WebControls.TextBox)grview.Rows[i].FindControl("txt_safe_qty");
            System.Web.UI.WebControls.Label labqty_product = (System.Web.UI.WebControls.Label)grview.Rows[i].FindControl("labqty_product");

            System.Web.UI.WebControls.TextBox txt_safe_qty = (System.Web.UI.WebControls.TextBox)grview.Rows[i].FindControl("txt_product_qty");
            System.Web.UI.WebControls.TextBox txtprice = (System.Web.UI.WebControls.TextBox)grview.Rows[i].FindControl("txtprice");
            System.Web.UI.WebControls.TextBox txtquantity = (System.Web.UI.WebControls.TextBox)grview.Rows[i].FindControl("txtqauntity");
            System.Web.UI.WebControls.HiddenField hidrowid = (System.Web.UI.WebControls.HiddenField)grview.Rows[i].FindControl("hidrowid");
            System.Web.UI.WebControls.HiddenField hidnid = (System.Web.UI.WebControls.HiddenField)grview.Rows[i].FindControl("hidnid");
            System.Web.UI.WebControls.HiddenField hdnprice = (System.Web.UI.WebControls.HiddenField)grview.Rows[i].FindControl("hdnprice");

            System.Web.UI.WebControls.HiddenField hd_nid = (System.Web.UI.WebControls.HiddenField)grview.Rows[i].FindControl("hd_nid");
            System.Web.UI.WebControls.HiddenField assign_id = (System.Web.UI.WebControls.HiddenField)grview.Rows[i].FindControl("hd_assign_id");


            foreach (DataRow row in dt.Rows)
            {

                if (row["rowid"].ToString() == hidrowid.Value)
                {
                    decimal price = 0;
                    decimal qty = 0;

                    if (!decimal.TryParse(hdnprice.Value, out price))
                        price = 0;

                    if (!decimal.TryParse(txtquantity.Text, out qty) || qty == 0)
                    {
                        continue;  // 👉 Go to next row (do not update)
                    }

                    decimal totalamount = price * qty;

                    row["catid"] = drpcategory.SelectedValue;
                    row["subcatid"] = drpsubcat.SelectedValue;
                    row["productid"] = drpproduct.SelectedValue;
                    row["labqty_product"] = labqty_product.Text;
                    row["txt_safe_qty"] = txt_safe_qty.Text;
                    row["txt_product_qty"] = txt_product_qty.Text;
                    row["price"] = hdnprice.Value;
                    row["totalprice"] = totalamount.ToString();
                    row["quantity"] = txtquantity.Text;


                }
            }



        }
        ViewState["product_table"] = dt;

    }



    protected void grview_RowDataBound(object sender, GridViewRowEventArgs e)
    {
        if (e.Row.RowType == DataControlRowType.DataRow)
        {
            HiddenField hidnid = (HiddenField)e.Row.FindControl("hidnid");
            LinkButton lnkRemove = (LinkButton)e.Row.FindControl("lnkremoveproduct");
            LinkButton lnkAdd2 = (LinkButton)e.Row.FindControl("lnkaddproduct");
            TextBox txtTotalPrice = (TextBox)e.Row.FindControl("txttotalprice");
            txtTotalPrice.Visible = true;

            // Manage Add/Remove visibility
            DataTable dt = ViewState["product_table"] as DataTable;
            if (dt != null)
            {
                if (dt.Rows.Count == row_index)
                {
                    lnkAdd2.Visible = true;
                    lnkRemove.Visible = false;
                }
                else
                {
                    lnkAdd2.Visible = false;
                    lnkRemove.Visible = true;
                }
                row_index++;
            }

            // --- Bind dropdowns safely ---
            DropDownList drpCategory = (DropDownList)e.Row.FindControl("drpcategory");
            DropDownList drpSubCategory = (DropDownList)e.Row.FindControl("ddlSubCategory");
            DropDownList drpProduct = (DropDownList)e.Row.FindControl("drpProduct");

            bindcategory(drpCategory);

            try { drpCategory.SelectedValue = DataBinder.Eval(e.Row.DataItem, "catid").ToString(); } catch { }

            fillsubcategory(drpCategory.SelectedValue, drpSubCategory);
            try { drpSubCategory.SelectedValue = DataBinder.Eval(e.Row.DataItem, "subcatid").ToString(); } catch { }

            fillproducts(drpSubCategory.SelectedValue, drpProduct);
            try { drpProduct.SelectedValue = DataBinder.Eval(e.Row.DataItem, "productid").ToString(); } catch { }

            // Hide qty boxes
            TextBox txtProductQty = (TextBox)e.Row.FindControl("txt_product_qty");
            TextBox txtSafeQty = (TextBox)e.Row.FindControl("txt_safe_qty");
            if (txtProductQty != null) txtProductQty.Visible = false;
            if (txtSafeQty != null) txtSafeQty.Visible = false;

            // Fetch per-product data
            HiddenField hd_nid = (HiddenField)e.Row.FindControl("hd_nid");

            //if (objda == null)
            //    objda = new DataAccess();

            //DataSet ds = objda.getdata(@"
            //SELECT *, 
            //       (A.purchase_price + ' - ' + A.selling_price + ' - ' + A.selling_percent + '%') AS PRO_DETAILS
            //FROM tblproduct_master AS A
            //JOIN tblproduct_safehouse AS B ON A.NID = B.product_master_id
            //WHERE B.nid = '" + hd_nid.Value + "'");

            if (ds != null && ds.Tables.Count > 0 && ds.Tables[0].Rows.Count > 0)
            {
                // Optional: display data in label
                // Label lblDetails = (Label)e.Row.FindControl("labproduct_details");
                // lblDetails.Text = ds.Tables[0].Rows[0]["PRO_DETAILS"].ToString();
            }

        }
    }


    protected void bindcategory(DropDownList drpcategory)
    {

        DataSet ds = objda.getdata("SELECT nid, jewellery_name FROM tbljewellery_type Where active_status='active'");
        drpcategory.DataSource = ds;
        drpcategory.DataTextField = "jewellery_name";
        drpcategory.DataValueField = "nid";
        drpcategory.DataBind();
        drpcategory.Items.Insert(0, new System.Web.UI.WebControls.ListItem("Select Category", ""));
        drpcategory.SelectedIndex = 0;

    }

    protected void drpcategory_SelectedIndexChanged(object sender, EventArgs e)
    {
        DropDownList ddlCategory = (DropDownList)sender;
        GridViewRow row = (GridViewRow)ddlCategory.NamingContainer;
        DropDownList ddlSubCategory = (DropDownList)row.FindControl("ddlSubCategory");


        fillsubcategory(ddlCategory.SelectedValue, ddlSubCategory);

        //if (ddlCategory.SelectedItem.Text.ToLower() == "stone")
        //{
        //    DataSet ds = new DataSet();
        //    ds = objda.getdata("select * from tblgeneric_data where value_type='Stone Category' and active_status='active'");
        //    if (ds.Tables[0].Rows.Count > 0)
        //    {
        //        ddlSubCategory.DataSource = ds;
        //        ddlSubCategory.DataTextField = "name";
        //        ddlSubCategory.DataValueField = "nid";
        //        ddlSubCategory.DataBind();
        //    }
        //}
        //else
        //{
        //}
    }

    public void fillsubcategory(string catid, DropDownList drpsubcategory)
    {

        DataSet ds = new DataSet();
        objda.action = "all_sub_category_by_category";
        objda.catid = catid;
        ds = objda.sub_category_master_mgmt();
        drpsubcategory.DataSource = ds;
        drpsubcategory.DataTextField = "sub_category";
        drpsubcategory.DataValueField = "nid";
        drpsubcategory.DataBind();
        drpsubcategory.Items.Insert(0, new System.Web.UI.WebControls.ListItem("Select Sub Category", ""));
        drpsubcategory.SelectedIndex = 0;

    }


    protected void drpsubcategory_SelectedIndexChanged(object sender, EventArgs e)
    {
        DropDownList drpsubcat = (DropDownList)sender;
        GridViewRow row = (GridViewRow)drpsubcat.NamingContainer;
        DropDownList drpproduct = (DropDownList)row.FindControl("drpProduct");

        fillproducts(drpsubcat.SelectedValue, drpproduct);

    }
    public void fillproducts(string subcatid, DropDownList drpproduct)
    {

        string subcat = subcatid;
        ds = objda.getdata("SELECT A.nid ,A.product_Name,B.quantity  FROM tblproduct_master as A JOIN tblproduct_safehouse AS B ON A.nid=B.product_master_id WHERE A.sub_category = '" + subcat + "' AND A.BSTATUS=1");
        drpproduct.DataSource = ds;
        drpproduct.DataTextField = "product_name";
        drpproduct.DataValueField = "nid";
        drpproduct.DataBind();
        drpproduct.Items.Insert(0, new System.Web.UI.WebControls.ListItem("Select Product", ""));
        drpproduct.SelectedIndex = 0;



    }

    protected void drpproduct_SelectedIndexChanged(object sender, EventArgs e)
    {
        DropDownList drpproduct = (DropDownList)sender;
        GridViewRow row = (GridViewRow)drpproduct.NamingContainer;
        ds = objda.getdata(@"
SELECT 
    A.*,
    A.quantity AS txt_product_qty,
    K.company_stock,
    K.remain_qty AS txt_safe_qty,
    CAST(A.selling_price AS DECIMAL(18,2)) 
        * ISNULL(A.Converte_rate,1) AS selling_price_peso

FROM tblproduct_master AS A

LEFT JOIN tblproduct_safehouse AS K 
    ON K.product_master_id = A.nid

LEFT JOIN tblcurrency_converter AS L 
    ON L.currency_id = A.CurrencyType

WHERE A.nid = " + Convert.ToInt32(drpproduct.SelectedValue) + @"
AND A.bstatus = 1
");


        HiddenField hndproductid = (HiddenField)row.FindControl("hidproductid");

        HiddenField hd_nid = (HiddenField)row.FindControl("hd_nid");
        HiddenField hdnprice = (HiddenField)row.FindControl("hdnprice");
        TextBox txt_qty = (TextBox)row.FindControl("txt_product_qty");
        TextBox txt_safe_qty = (TextBox)row.FindControl("txt_safe_qty");
        Label labqty_product = (Label)row.FindControl("labqty_product");
        TextBox txtprice = (TextBox)row.FindControl("txtprice");

        if (ds.Tables[0].Rows.Count > 0)
        {
            hndproductid.Value = drpproduct.SelectedValue;

            DataRow drItem = ds.Tables[0].Rows[0];

            labqty_product.Text = "P.Q - " + drItem["txt_product_qty"].ToString() +
                                  " , SH.Q - " + drItem["txt_safe_qty"].ToString() +
                                  " , C.Q - " + drItem["company_stock"].ToString();


            txt_qty.Text = "Purchase Qty -> " + drItem["txt_product_qty"].ToString();
            txt_safe_qty.Text = "S. House Qty -> " + drItem["txt_safe_qty"].ToString();

            ViewState["safe_qty"] = drItem["txt_safe_qty"].ToString();

            if (string.IsNullOrEmpty(ViewState["safe_qty"].ToString()))
            {
                ViewState["safe_qty"] = "0";
            }

            txtprice.Text = "Unit Price - " + drItem["selling_price"].ToString();
            hdnprice.Value = drItem["selling_price"].ToString();
        }


    }

    protected void btn_barcode_click(object sender, EventArgs e)
    {

        // Get LinkButton reference
        LinkButton btn = sender as LinkButton;
        GridViewRow row = (GridViewRow)btn.NamingContainer;
        ViewState["rowIndex"] = row.RowIndex;
        DropDownList drpcategory = (DropDownList)row.FindControl("drpcategory");
        DropDownList ddlSubCategory = (DropDownList)row.FindControl("ddlSubCategory");
        DropDownList drpProduct = (DropDownList)row.FindControl("drpProduct");
        HiddenField hid = (HiddenField)row.FindControl("hidproductid");
        HiddenField hd_assign_id = (HiddenField)row.FindControl("hd_assign_id");
        string productId = drpProduct.SelectedValue;
        if (productId == null || productId == "")
        {
            ClientScript.RegisterStartupScript(this.GetType(), "alert", "alert('Select Product');", true);
            return;
        }
        ViewState["drpcategory"] = drpcategory.SelectedValue;
        ViewState["ddlSubCategory"] = ddlSubCategory.SelectedValue;
        ViewState["productid"] = productId;
        ViewState["assign_id"] = hd_assign_id.Value;
        fillbardata();
        bindbarcode();
        divpaymnet.Visible = false;
        divbarcode.Visible = true;
        ClientScript.RegisterStartupScript(typeof(Page), "temp", "<script type='text/javascript'>openbarcodepopup();</script>");



        //// Register JS to call your popup
        //string script = "openbarcodePopup('" + productId + "');";
        //ScriptManager.RegisterStartupScript(this, this.GetType(), "popup", script, true);
    }
    //protected void GridView1_PageIndexChanging(object sender, GridViewPageEventArgs e)
    //{
    //    GridView1.PageIndex = e.NewPageIndex;
    //    bindbarcode();
    //}
    protected void drpresellername_click(object sender, EventArgs e)
    {

        string id = drpname.SelectedItem.Value;
        bindgrid();
    }
    protected void drpdrppaymnetstatus_click(object sender, EventArgs e)
    {
        if (ViewState["assigntable"] != null)
        {
            DataTable dt = (DataTable)ViewState["assigntable"];
            DataView dv = new DataView(dt);

            if (!string.IsNullOrEmpty(drppaymnetstatus.SelectedValue))
            {
                string status = drppaymnetstatus.SelectedValue;

                dv.RowFilter = "payment = '" + status.Replace("'", "''") + "'";
            }
            else
            {
                dv.RowFilter = ""; // Show all
            }

            grvAssign.DataSource = dv;
            grvAssign.DataBind();
        }
    }


    public string generatequerypop(string type)
    {
        if (ViewState["productid"] == null)
        {
            return "";
        }

        string sql = "";
        if (type == "GRID")
        {
            if (ViewState["editnid"] != null)
            {
                sql = "SELECT NID,barcode_number FROM tblproduct_detail_master WHERE product_masterid='" + ViewState["productid"].ToString() + "' and ( sold_status='pending' or sold_status='assign' )";
            }
            else
            {
                if (drpReseller.SelectedItem.Value == "")
                {
                    //  ClientScript.RegisterStartupScript(this.GetType(), "alert", "alert('First Seelect Reseller Name');", true);

                    Page.ClientScript.RegisterStartupScript(
                        typeof(Page),
                        "alert",
                        "<script language='javascript'>alert('First Select Reseller Name.');</script>"
                    );

                    return "";
                }
                sql = "SELECT NID,barcode_number FROM tblproduct_detail_master WHERE product_masterid='" + ViewState["productid"].ToString() + "' and assign_status='pending'\r\nand" +
                    " sold_status='pending' and barcode_number not in \r\n(select barcode from tblreserved_items\r\nwhere reserve_master_id not" +
                    " in \r\n(SELECT nid from tblreserved_master where reseller_id='" + drpReseller.SelectedItem.Value + "')\r\n)";

            }
        }
        else
        {
            sql = "SELECT B.jewellery_name,C.sub_category,product_Name FROM tblproduct_master AS A \r\nJOIN\r\ntbljewellery_type AS B ON A.category=B.nid\r\nJOIN\r\ntblsub_category_master AS C ON A.sub_category=C.nid WHERE A.nid='" + ViewState["productid"].ToString() + "'" +
                " \r\n\tselect quantity from tblProductAssign where nid='" + ViewState["assign_id"] + "'";

        }
        return sql;
    }
    public void fillbardata()
    {
        ds = objda.getdata(generatequerypop(""));

        if (ds.Tables[0].Rows.Count > 0)
        {
            txtcategory.Text = ds.Tables[0].Rows[0]["jewellery_name"].ToString();
            txtsubcategory.Text = ds.Tables[0].Rows[0]["sub_category"].ToString();
            txtproduct.Text = ds.Tables[0].Rows[0]["product_Name"].ToString();
        }
        if (ds.Tables[1].Rows.Count > 0)
        {
            ViewState["countbarcode"] = ds.Tables[1].Rows[0]["quantity"].ToString();

        }

    }
    public void bindbarcode()
    {
        ds = objda.getdata(generatequerypop("GRID"));
        if (ds.Tables.Count > 0 && ds.Tables[0].Rows.Count > 0)
        {
            GridView1.DataSource = ds;
            GridView1.DataBind();

        }
        else
        {
            GridView1.DataSource = null;
            GridView1.DataBind();
        }
    }
    protected void GridView1_RowDataBound(object sender, GridViewRowEventArgs e)
    {
        if (e.Row.RowType == DataControlRowType.DataRow)
        {
            System.Web.UI.WebControls.CheckBox chk = e.Row.FindControl("chkEditRec") as System.Web.UI.WebControls.CheckBox;
            if (chk != null)
            {
                string nid = chk.ToolTip;
                if (e.Row.RowType == DataControlRowType.DataRow)
                {
                    if (ViewState["rowIndex"] == null)
                    {
                        return;
                    }

                    DataTable dt = (DataTable)ViewState["barcode_table"];
                    DataView dv = new DataView(dt);
                    int index = (int)ViewState["rowIndex"];


                    //ViewState["productid"] = drpcategory.SelectedValue;
                    //ViewState["ddlSubCategory"] = ddlSubCategory.SelectedValue;
                    //ViewState["productid"] = productId;

                    string catid = ViewState["drpcategory"].ToString();
                    string subcatid = ViewState["ddlSubCategory"].ToString();
                    string productid = ViewState["productid"].ToString();
                    dv.RowFilter = "catid = '" + catid + "' AND subcatid = '" + subcatid + "' AND productid = '" + productid + "'";// apply filter on DataView




                    if (dv.Count > 0)
                    {
                        for (int i = 0, j = 1; i < dv.Count; i++)
                        {
                            DataRowView drv = dv[i];

                            // Access values
                            string barcodenid = drv["barcodenid"].ToString();
                            if (nid == barcodenid)
                            {
                                chk.Checked = true;

                            }
                        }
                    }
                }

            }
        }


    }
    public void removebartable(string catid, string subcatid, string productid)
    {
        if (ViewState["barcode_table"] != null)
        {
            DataTable dt = (DataTable)ViewState["barcode_table"];

            if (dt.Rows.Count > 0)
            {
                DataRow[] rows = dt.Select("catid = '" + catid + "'  AND subcatid = '" + subcatid + "' AND productid = '" + productid + "'");

                foreach (DataRow rowToDelete in rows)
                {
                    dt.Rows.Remove(rowToDelete);
                }

                // Accept changes (optional, keeps table clean)
                dt.AcceptChanges();

                // Update ViewState
                ViewState["barcode_table"] = dt;
            }
        }
    }
    protected void btnsubmit_Click(object sender, EventArgs e)
    {
        int selectindex = 0;
        foreach (GridViewRow row in GridView1.Rows)
        {

            System.Web.UI.WebControls.CheckBox chk = (System.Web.UI.WebControls.CheckBox)row.FindControl("chkEditRec");
            if (chk != null && chk.Checked)
            {

                selectindex++;
                if (ViewState["safe_qty"] != null)
                {
                    int saf_qty = Convert.ToInt32(ViewState["safe_qty"].ToString());
                    if (selectindex > saf_qty)
                    {
                        Page.ClientScript.RegisterStartupScript(
                            typeof(Page),
                            "alert",
                            "<script language='javascript'>alert('For this product, only " + saf_qty + " Safe House Qty is available.');</script>"
                        );
                        return;
                    }
                }

            }
        }

        if (ViewState["barcode_table"] != null)
        {
            DataTable dt = (DataTable)ViewState["barcode_table"];

            if (dt.Rows.Count > 0)
            {
                string catid = ViewState["drpcategory"].ToString();
                string subcatid = ViewState["ddlSubCategory"].ToString();
                string productid = ViewState["productid"].ToString();
                // dv.RowFilter = "catid = '" + catid + "' AND subcatid = '" + subcatid + "' AND productid = '" + productid + "'";// apply filter on DataView
                // Use Select to filter rows
                DataRow[] rows = dt.Select("catid = '" + catid + "'  AND subcatid = '" + subcatid + "' AND productid = '" + productid + "'");

                foreach (DataRow rowToDelete in rows)
                {
                    dt.Rows.Remove(rowToDelete);
                }

                // Accept changes (optional, keeps table clean)
                // dt.AcceptChanges();

                // Update ViewState
                ViewState["barcode_table"] = dt;
            }
        }




        int count = 0;
        int rowid = 0;
        if (ViewState["barcode_table"] != null)
        {
            DataTable dt = (DataTable)ViewState["barcode_table"];

            object result = dt.Compute("MAX(rowid)", string.Empty);
            if (result != DBNull.Value)
            {
                rowid = Convert.ToInt32(result) + 1;
            }
        }
        else
        {
            rowid = 1;
        }


        foreach (GridViewRow row in GridView1.Rows)
        {
            System.Web.UI.WebControls.CheckBox chk = (System.Web.UI.WebControls.CheckBox)row.FindControl("chkEditRec");
            if (chk != null && chk.Checked)
            {
                string nid = chk.ToolTip;
                count++;
                savebarcodedatatable(nid, rowid);
            }
        }


        if (ViewState["rowIndex"] != null)
        {
            int rowIndex = Convert.ToInt32(ViewState["rowIndex"]);

            GridViewRow row = grview.Rows[rowIndex];
            TextBox txtqauntity = (TextBox)row.FindControl("txtqauntity");
            txtqauntity.Text = count.ToString();
            TextBox txttotalprice = (TextBox)row.FindControl("txttotalprice");
            HiddenField hdnprice = (HiddenField)row.FindControl("hdnprice");
            decimal price = Convert.ToDecimal(hdnprice.Value);

            txttotalprice.Text = "Total Price - " + (count * price).ToString("0.00"); txttotalprice.Visible = true;
        }
        CalculateTotals();
    }

    public void createbarcodedatatable()
    {
        DataTable dt = new DataTable();
        DataColumn dc = new DataColumn("catid", typeof(string));
        dt.Columns.Add(dc);
        dc = new DataColumn("subcatid", typeof(string));
        dt.Columns.Add(dc);
        dc = new DataColumn("productid", typeof(string));
        dt.Columns.Add(dc);
        dc = new DataColumn("barcodenid", typeof(string));
        dt.Columns.Add(dc);
        dc = new DataColumn("rowid", typeof(string));
        dt.Columns.Add(dc);
        ViewState["barcode_table"] = dt;
    }

    //public void add_barcode_row()
    //{
    //    if (ViewState["barcode_table"] == null)
    //    {
    //        createbarcodedatatable();
    //    }
    //    DataTable dt = (DataTable)ViewState["barcode_table"];
    //    int rowid = 0;
    //    object result = dt.Compute("MAX(rowid)", string.Empty);
    //    if (result != DBNull.Value)
    //    {
    //        rowid = Convert.ToInt32(result);
    //    }
    //    rowid++;
    //    DataRow dr = dt.NewRow();
    //    dr["catid"] = "0";
    //    dr["subcatid"] = "0";
    //    dr["productid"] = "0";
    //    dr["barcodenid"] = "0";
    //    dr["rowid"] = "0";
    //    dt.Rows.Add(dr);
    //}

    public void savebarcodedatatable(string nid, int rowid)
    {
        if (ViewState["rowIndex"] != null)
        {
            int rowindex = (int)ViewState["rowIndex"];

            DropDownList drpcategory = (DropDownList)grview.Rows[rowindex].FindControl("drpcategory");
            DropDownList drpsubcat = (DropDownList)grview.Rows[rowindex].FindControl("ddlSubCategory");
            DropDownList drpproduct = (DropDownList)grview.Rows[rowindex].FindControl("drpProduct");

            if (ViewState["barcode_table"] == null)
            {
                createbarcodedatatable();
            }
            DataTable dt = (DataTable)ViewState["barcode_table"];

            DataRow dr = dt.NewRow();
            dr["catid"] = drpcategory.SelectedValue;
            dr["subcatid"] = drpsubcat.SelectedValue;
            dr["productid"] = drpproduct.SelectedValue;
            dr["barcodenid"] = nid;
            dr["rowid"] = rowid;
            dt.Rows.Add(dr);


        }



        //  DataTable dt = (DataTable)ViewState["barcode_table"];
        //if (dt == null) return;

        //if (ViewState["rowIndex"] != null)
        //{
        //    int rowindex = (int)ViewState["rowIndex"];

        //    DropDownList drpcategory = (DropDownList)grview.Rows[rowindex].FindControl("drpcategory");
        //    DropDownList drpsubcat = (DropDownList)grview.Rows[rowindex].FindControl("ddlSubCategory");
        //    DropDownList drpproduct = (DropDownList)grview.Rows[rowindex].FindControl("drpProduct");

        //    // Example: Update row in DataTable with dropdown values
        //    foreach (DataRow dr in dt.Rows)
        //    {
        //        if (dr["rowid"].ToString() == rowindex.ToString()) // Or use hidden field for exact match
        //        {
        //            dr["catid"] = drpcategory.SelectedValue;
        //            dr["subcatid"] = drpsubcat.SelectedValue;
        //            dr["productid"] = drpproduct.SelectedValue;
        //            break;
        //        }
        //    }
        //}

        //// Example: iterate through GridView checkboxes
        //for (int i = 0; i < GridView1.Rows.Count; i++)
        //{
        //    System.Web.UI.WebControls.CheckBox chkEditRec = (System.Web.UI.WebControls.CheckBox)GridView1.Rows[i].FindControl("chkEditRec");
        //    if (chkEditRec != null && chkEditRec.Checked)
        //    {
        //        // Do something with checked rows
        //    }
        //}

        //// Save back to ViewState
        //ViewState["barcode_table"] = dt;
    }








    protected void btn_fillter_click(object sender, EventArgs e)
    {
        bindgrid();
    }

    protected void grvAssign_PageIndexChanging(object sender, GridViewPageEventArgs e)
    {
        grvAssign.PageIndex = e.NewPageIndex;
        bindgrid();
    }

    protected void lnkexport_Click(object sender, EventArgs e)
    {
        ds = objda.getdata(generatequery("excel"));
        excelexport objexport = new excelexport();
        objexport.ExportDataSetToExcel(ds, "Reseller_List.xls");
    }

    protected void btnBack_Click(object sender, EventArgs e)
    {
        mview.ActiveViewIndex = 0;
        clearform();
        ViewState["editnid"] = null;
    }
}