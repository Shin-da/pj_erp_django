<%@ Page Title="Product Assign" Language="C#" MasterPageFile="~/iadmin/meresellermaster.master" ValidateRequest="false" AutoEventWireup="true" CodeFile="productassign.aspx.cs" Inherits="productassign" MaintainScrollPositionOnPostback="true" %>

<asp:Content ID="Content1" ContentPlaceHolderID="head" runat="Server">
    <link rel="stylesheet" type="text/css" href="js/datetimepicker/jquery.datetimepicker.css" />
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/jquery-datetimepicker@2.5.20/jquery.datetimepicker.min.css">
    <link href="https://cdn.jsdelivr.net/npm/select2@4.1.0-rc.0/dist/css/select2.min.css" rel="stylesheet" />
      <script src="/Assets/js/sync-loader.js"></script>
    <script type="text/javascript">
        function openPrintFile() {
            window.open('/path/to/print.html', '_blank');
        }

        function check_uncheck() {
            var ValChecked = document.getElementById("ContentPlaceHolder1_grview_chkhead").checked;

            // Loop through all elements
            for (i = 0; i < document.forms[0].length; i++) {
                if (document.forms[0].elements[i].type == "checkbox") {
                    if (ValChecked == true) {
                        document.forms[0].elements[i].checked = true;
                    }
                    else {
                        document.forms[0].elements[i].checked = false;
                    }
                }
            }
        }

    </script>


    <script type="text/javascript">
        function openbarcodepopup() {
            const modal = document.getElementById("divaddnewbarcode");
            const overlay = document.getElementById("otherbarcodebg");

            modal.style.display = "block";
            overlay.style.display = "block";

            const screenWidth = window.innerWidth || document.body.offsetWidth;
            const modalWidth = 900;
            const leftOffset = (screenWidth - modalWidth) / 2;

            modal.style.left = leftOffset + "px";
            modal.style.top = "60px";
        }

        function closebarcodepopup() {
            document.getElementById("divaddnewbarcode").style.display = "none";
            document.getElementById("otherbarcodebg").style.display = "none";
        }

    </script>


    <style>
  
        .overlay-bg {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background-color: rgba(0,0,0,0.5);
            z-index: 999;
        }

        .newpopupdiv, .newpopupsalarydiv {
            position: absolute;
            background: #fff;
            z-index: 1000;
            box-shadow: 0px 4px 10px rgba(0, 0, 0, 0.2);
            border-radius: 6px;
        }

        .btn-success {
            background-color: #28a745;
            color: #fff;
        }

        .btn-fail {
            background-color: var(--pj-status-blue);
            color: #fff;
        }

  
        .btn-group-room {
            display: inline-flex;
            gap: 4px;
        }

        .btn-add-room {
            background-color: #343a40;
            color: #fff;
            border: none;
            border-radius: 4px;
            padding: 3px 7px;
            font-size: 12px;
            cursor: pointer;
            transition: 0.2s;
            display: inline-flex;
            align-items: center;
        }

            .btn-add-room:hover {
                background-color: #000;
            }

            .btn-add-room i {
                font-size: 10px;
            }

        .refresh-btn {
            background-color: #007bff;
        }

            .refresh-btn:hover {
                background-color: #0056b3;
            }

        /* ---------------------------------------------------------
   GRIDVIEW ACTION BUTTONS (Invoice + Edit)
--------------------------------------------------------- */
        .action-buttons {
            display: flex;
            align-items: center;
            gap: 6px;
        }

        /* Invoice Button */
        .gv-btn {
            padding: 3px 8px;
            font-size: 11px;
            border-radius: 4px;
            background: #007bff;
            color: #fff !important;
            border: 1px solid transparent;
            transition: .2s;
        }

            .gv-btn:hover {
                background: #0056b3;
                text-decoration: underline !important;
            }

        /* Small black icon buttons (Edit / Return / Status / All icons) */
        /* Small light-black icons */
        .icon-btn {
            font-size: 15px !important;
            padding: 3px 5px;
            color: #555 !important; /* LIGHT BLACK */
            border-radius: 4px;
            background: #f8f9fa;
            border: 1px solid transparent;
            display: inline-flex;
            align-items: center;
            cursor: pointer;
            transition: all .2s ease;
            text-decoration: none !important; /* No underline always */
        }

            /* Hover: soft highlight, NO underline */
            .icon-btn:hover {
                background: #eaeaea; /* soft grey */
                border-color: #aaa; /* soft border */
                text-decoration: none !important; /* force no underline */
            }


        /* ---------------------------------------------------------
   RETURN + STATUS WRAP
--------------------------------------------------------- */
        .return-status-wrap {
            display: flex;
            align-items: center;
            gap: 12px;
        }
    </style>



</asp:Content>

<asp:Content ID="Content2" ContentPlaceHolderID="ContentPlaceHolder1" runat="Server">
    <div class="container">
        <asp:MultiView ID="mview" runat="server" ActiveViewIndex="0">
            <asp:View ID="View1" runat="server">


                <div class="col-md-12 col-xs-12 bg_white">
                    <div class="col-md-12 heading_bg nopl_mb mb20">
                        <h1 class="nomt nomb">Product Assign</h1>
                    </div>
                    <div class="clearfix"></div>
                    <div class="col-md-12 ">
                        <fieldset class="scheduler-border">
                            <div class="col-md-12 text-center">
                                <br />
                                <asp:Button ID="btnAddNew" runat="server" Text="Assign New Product" CssClass="btn btn_add"
                                    OnClick="btnAddNew_Click" />
                            </div>
                        </fieldset>
                    </div>
                    <div class="col-md-3 form-group">
                        <label>Reseller Name</label>
                        <asp:DropDownList runat="server" ID="drpname" AutoPostBack="true"
                            OnSelectedIndexChanged="drpresellername_click"
                            class="form-control" ClientIDMode="Static">
                        </asp:DropDownList>
                    </div>
                    <div class="col-md-3 form-group">
                        <label>Invoice Number</label>
                        <asp:DropDownList runat="server" ID="drpinvoicenumber" AutoPostBack="true"
                            OnSelectedIndexChanged="drpresellername_click"
                            class="form-control"
                            ClientIDMode="Static">
                        </asp:DropDownList>
                    </div>
                    <div class="col-md-3 form-group">
                        <label>Payment Status</label>
                        <asp:DropDownList runat="server" ID="drppaymnetstatus" AutoPostBack="true" OnSelectedIndexChanged="drpdrppaymnetstatus_click" class="form-control" Placeholder="Reseller Name">
                            <asp:ListItem Text="Select Payment Status" Value=""></asp:ListItem>
                            <asp:ListItem Text="Complete" Value="complete"></asp:ListItem>
                            <asp:ListItem Text="Pending" Value="pending"></asp:ListItem>
                            <asp:ListItem Text="Cleared" Value="Cleared"></asp:ListItem>
                        </asp:DropDownList>
                    </div>
                    <div class="col-md-3 form-group">
                        <label>Return Status</label>
                        <asp:DropDownList runat="server" ID="drpreturnstatus" AutoPostBack="true" OnSelectedIndexChanged="drpresellername_click" class="form-control" Placeholder="Reseller Name">
                            <asp:ListItem Text="Select Return Status" Value=""></asp:ListItem>
                            <asp:ListItem Text="Complete" Value="complete"></asp:ListItem>
                            <asp:ListItem Text="Pending" Value="pending"></asp:ListItem>
                        </asp:DropDownList>
                    </div>
                    <div class="clearfix"></div>
                    <div class="col-md-3 form-group">
                        <label>From Date</label>
                        <asp:TextBox CssClass="form-control custom-input" ID="txtfromdate" runat="server"
                            onblur="validformat(this.id);" placeholder="Select From Date" AutoPostBack="true" OnTextChanged="btn_fillter_click">
                        </asp:TextBox>
                    </div>

                    <div class="col-md-3 form-group">
                        <label>To Date</label>
                        <asp:TextBox CssClass="form-control custom-input" ID="txttodate" runat="server"
                            onblur="validformat(this.id);" placeholder="Select To Date" AutoPostBack="true" OnTextChanged="btn_fillter_click">
                        </asp:TextBox>
                    </div>


                    <div class="col-md-6 form-group">
                        <asp:LinkButton ID="lnkexport" runat="server" OnClick="lnkexport_Click" ToolTip="Export To Excel" Style="margin: 2px;">
                            <img src="images/excel.png" alt="Export to Excel" style="height: 30px; width: auto;" />
                        </asp:LinkButton>
                    </div>

                    <div class="form-group" style="margin-bottom:8px;">
                        <input type="text" id="txtAssignSearch" class="form-control" placeholder="Search assignments..."
                            onkeyup="filterAssignGrid(this.value);" style="max-width:400px;" />
                    </div>
                    <div class="pj-grid-scroll">
                    <asp:GridView ID="grvAssign" Width="98%" CssClass="pj-grid" runat="server" AutoGenerateColumns="False"
                        GridLines="Both" CellPadding="5"
                        ShowHeader="true" DataKeyNames="nid" ShowFooter="true" OnRowCommand="grvAssign_RowCommand" OnRowDataBound="grview2_RowDataBound"
                        AllowPaging="True" PageSize="25" OnPageIndexChanging="grvAssign_PageIndexChanging">


                        <Columns>

                            <asp:TemplateField HeaderText="SNo">
                                <ItemTemplate>
                                    <%# Container.DataItemIndex + 1 %>
                                </ItemTemplate>
                            </asp:TemplateField>

                            <%--  <asp:BoundField DataField="Product_Id" HeaderText="Product" />--%>
                            <asp:BoundField DataField="name" HeaderText="Reseller Name" />
                            <asp:BoundField DataField="invoice_number" HeaderText="Invoice Number" />
                            <asp:TemplateField HeaderText="Assign Date">
                                <ItemTemplate>
                                    <%# Convert.ToDateTime(Eval("assign_date")).ToString("MMMM dd, yyyy") %>
                                </ItemTemplate>
                            </asp:TemplateField>



                            <asp:BoundField DataField="total_quantity"
                                HeaderText="Assign Quantity"
                                DataFormatString="{0:0}"
                                HtmlEncode="false" />

                            <asp:BoundField DataField="return_quantity"
                                HeaderText="Return Quantity"
                                DataFormatString="{0:0}"
                                HtmlEncode="false" />

                            <asp:BoundField DataField="sold_quantity"
                                HeaderText="Sold Quantity"
                                DataFormatString="{0:0}"
                                HtmlEncode="false" />

                            <asp:BoundField DataField="pending_quantity"
                                HeaderText="Pending Quantity"
                                DataFormatString="{0:0}"
                                HtmlEncode="false" />

                            <asp:BoundField
                                DataField="total_price"
                                HeaderText="Total Price"
                                DataFormatString="{0:N4}"
                                HtmlEncode="false" />



                            <asp:TemplateField HeaderText="Return - Status">
                                <ItemTemplate>
                                    <div class="return-status-wrap">

                                        <!-- Return Button -->
                                        <asp:LinkButton
                                            runat="server"
                                            CommandName="return"
                                            CommandArgument='<%# Eval("nid") %>'
                                            ToolTip="Return"
                                            CssClass="fa fa-reply icon-btn">
                                        </asp:LinkButton>

                                        <!-- Status Icon -->
                                        <asp:LinkButton
                                            ID="txt_return"
                                            runat="server"
                                            CssClass='<%# 
                    (Eval("return_status").ToString().ToLower() == "complete" 
                        ? "fa fa-check icon-btn"
                        : "fa fa-clock icon-btn") 
                %>'>
                                        </asp:LinkButton>
                                        <asp:HiddenField
                                            ID="hidinvoicecanclestatus"
                                            runat="server"
                                            Value='<%# Eval("adminapproval_invoicecancle") %>' />
                                        <asp:HiddenField
                                            ID="hidreturn_status"
                                            runat="server"
                                            Value='<%# Eval("return_status") %>' />
                                    </div>
                                </ItemTemplate>
                            </asp:TemplateField>


                            <asp:TemplateField HeaderText="Payment Status">
                                <ItemTemplate>
                                    <span style='<%# 
            Eval("payment").ToString() == "complete" ? "color:#28a745;font-weight:600;": Eval("payment").ToString() == "cleaier" ? "color:#17a2b8;font-weight:600;" :
            "color:#ffc107;font-weight:600;" 
        %>'>

                                        <%# 
                Eval("payment").ToString() == "complete" ? "Complete" :
                Eval("payment").ToString() == "Cleared" ? "Cleared" :
                "Pending"
                                        %>

                                    </span>
                                </ItemTemplate>
                            </asp:TemplateField>





                            <asp:TemplateField HeaderText=" Payment ">
                                <ItemTemplate>
                                    <asp:HiddenField ID="hdassignmaster_id" runat="server" Value='<%# Eval("nid") %>' />
                                    <asp:Button runat="server" OnClick="btn_payment_click" BackColor="#008b8b" CommandArgument='<%# Eval("nid") %>' Text="Product Payment" CssClass="gv-btn" />

                                       <asp:HiddenField ID="hndassignpaymnet" runat="server" Value='<%# Eval("payment") %>' />
                                    <asp:Button runat="server" ID="btninvoice" Visible="false" CommandName="viewinvoice" CommandArgument='<%# Eval("invoice_data") %>' Text="Payment Receipt" CssClass="gv-btn" />

                                </ItemTemplate>
                            </asp:TemplateField>
                            <asp:TemplateField HeaderText="Action">
                                <ItemTemplate>
                                    <div class="action-buttons">

                                        <asp:Button
                                            ID="btnViewInvoice"
                                            runat="server"
                                            CommandName="Payment_invoice"
                                            CommandArgument='<%# Eval("nid") %>'
                                            Text="View Invoice"
                                            CssClass="gv-btn" BackColor="#008b8b" />

                                        <asp:Button
                                            ID="btnCancelInvoice"
                                            runat="server"
                                            CommandName="invoice_cancel"
                                            CommandArgument='<%# Eval("nid") %>'
                                            Text="Cancel Invoice"
                                            CssClass="gv-btn" BackColor="#008b8b" />

                                        <asp:LinkButton
                                            ID="btnEdit"
                                            runat="server"
                                            CommandName="editrec"
                                            CommandArgument='<%# Eval("nid") %>'
                                            CssClass="fa fa-edit icon-btn"
                                            ToolTip="Edit">
                                        </asp:LinkButton>

                                    </div>
                                </ItemTemplate>
                            </asp:TemplateField>




                        </Columns>
                    </asp:GridView>
                    </div>
                </div>
            </asp:View>

            <asp:View ID="View2" runat="server">
                <div class="col-md-12 col-xs-12 bg_white">
                    <div class="col-md-12 heading_bg nopl_mb mb20">
                        <h3 class="nomt nomb">Assign Product</h3>
                    </div>
                    <fieldset class="scheduler-border">
                        <legend class="scheduler-border">Product Detail</legend>
                        <div class="col-md-12">

                            <div class="col-md-3 form-group">
                                <div class="d-flex align-items-center justify-content-between mb-1">
                                    <label class="form-label mb-0">Reseller</label>
                                    <div class="btn-group-room">
                                        <asp:LinkButton ID="btnAddReseller" runat="server" ToolTip="Add New Reseller"
                                            OnClientClick="openResellerPopup(); return false;" CssClass="btn-add-room">
                <i class="fas fa-plus"></i>
                                        </asp:LinkButton>

                                        <asp:LinkButton ID="btnRefreshReseller" runat="server" ToolTip="Refresh Reseller List"
                                            OnClick="btnResellerRefresh_Click" CssClass="btn-add-room refresh-btn" UseSubmitBehavior="false">
                <i class="fas fa-sync-alt"></i>
                                        </asp:LinkButton>
                                    </div>
                                </div>

                                <asp:DropDownList ID="drpReseller" runat="server" CssClass="form-control" AutoPostBack="true" OnSelectedIndexChanged="drpReseller_selectclick"></asp:DropDownList>
                            </div>
                            <div class="col-md-3 form-group">
                                <label>Reseller Location</label>
                                <asp:DropDownList ID="drpresellerlocation" class="form-control" runat="server" Placeholder="Select Location "></asp:DropDownList>
                            </div>
                            <div class="col-md-3 form-group">
                                <label>Date</label>
                                <asp:TextBox CssClass="form-control custom-input" ID="txtDate" runat="server"
                                    onblur="validformat(this.id);" placeholder="Select Date" required="true">
                                </asp:TextBox>
                                <asp:RequiredFieldValidator ID="RequiredFieldValidator1" runat="server" ControlToValidate="txtDate"
                                    ErrorMessage="Please Fill Date" CssClass="text-danger" Display="Dynamic"
                                    ValidationGroup="ServiceGroup" />
                            </div>

                            <div class="col-md-3 form-group">
                                <label>Room No.</label>
                                <asp:DropDownList ID="drproomnumber" class="form-control" runat="server" Placeholder="Select Room "></asp:DropDownList>
                            </div>
                            <div class="col-md-3" style="margin-top: 28px" runat="server" visible="false">
                                <label>

                                    <asp:LinkButton ID="btnInfo" runat="server" CommandName="Info" ToolTip="Info"
                                        OnClientClick="openSubCategoryPopup(); return false;" CssClass="btn_black_a">
                                        <i class="fas fa-plus"></i>
                                    </asp:LinkButton>
                                    : Add Sub Category</label>
                            </div>
                            <div class="col-md-3" style="margin-top: 28px" runat="server" visible="false">
                                <label>

                                    <asp:LinkButton ID="btnInfo1" runat="server" CommandName="Info" ToolTip="Info"
                                        OnClientClick="openProductPopup(); return false;" CssClass="btn_black_a">
                                        <i class="fas fa-plus"></i>
                                    </asp:LinkButton>
                                    :Add Product</label>
                            </div>



                            <div class="col-md-12" style="overflow-x: auto;">
                                <asp:GridView ID="grview" Width="98%" CssClass="gridview" runat="server" AutoGenerateColumns="False"
                                    GridLines="Both" CellPadding="5" BackColor="White" BorderColor="#999999"
                                    BorderStyle="Solid" BorderWidth="1px" CellSpacing="1" RowStyle-HorizontalAlign="Center"
                                    ShowHeader="true" DataKeyNames="nid" ShowFooter="true" OnRowCommand="grview_RowCommand" OnRowDataBound="grview_RowDataBound"
                                    AllowPaging="false">

                                    <Columns>
                                        <asp:TemplateField HeaderText="Category">
                                            <ItemTemplate>
                                                <asp:DropDownList ID="drpcategory" runat="server" CssClass="form-control" Width="155"
                                                    AutoPostBack="true" OnSelectedIndexChanged="drpcategory_SelectedIndexChanged" />
                                            </ItemTemplate>
                                        </asp:TemplateField>
                                        <asp:TemplateField HeaderText="Sub Category">
                                            <ItemTemplate>
                                                <asp:DropDownList ID="ddlSubCategory" runat="server" CssClass="form-control" Width="155"
                                                    AutoPostBack="true" OnSelectedIndexChanged="drpsubcategory_SelectedIndexChanged" />

                                            </ItemTemplate>
                                        </asp:TemplateField>
                                        <asp:TemplateField HeaderText="Product Name - Quantity">
                                            <ItemTemplate>
                                                <asp:DropDownList ID="drpProduct" runat="server" CssClass="form-control" Width="180"
                                                    AutoPostBack="true" OnSelectedIndexChanged="drpproduct_SelectedIndexChanged" />
                                                <asp:Label ID="labqty_product" runat="server" Text='<%#   Eval("txt_product_qty") %>' Width="155" CssClass="form-control" BorderStyle="None"></asp:Label>
                                                <asp:TextBox ID="txt_product_qty" runat="server" Text='<%#   Eval("txt_product_qty") %>' Width="155" CssClass="form-control" ReadOnly="true" Visible="false" BorderStyle="None"></asp:TextBox>
                                                <asp:TextBox ID="txt_safe_qty" runat="server" Text='<%#   Eval("txt_safe_qty") %>' Width="155" CssClass="form-control" ReadOnly="true" Visible="false" BorderStyle="None"></asp:TextBox>

                                            </ItemTemplate>
                                        </asp:TemplateField>

                                        <asp:TemplateField HeaderText="Product List">
                                            <ItemTemplate>
                                                <asp:HiddenField ID="hidproductid" runat="server" />
                                                <asp:LinkButton ID="lnkproduct_list" runat="server"
                                                    CssClass="btn btn-success"
                                                    OnClick="btn_barcode_click">List
                                                    <i class="fas fa-list-check"></i>
                                                    <!-- checklist style -->
                                                </asp:LinkButton>
                                            </ItemTemplate>
                                        </asp:TemplateField>


                                        <%--    <asp:TemplateField HeaderText="(P.Price,S.P.,S.P.%)" Visible="false">
                                            <ItemTemplate>
                                                <asp:Label ID="labproduct_details" runat="server" />

                                                <asp:Label ID="labP_Price" Text="PP:" runat="server"></asp:Label>
                                                <br />
                                                <asp:Label ID="labselling_Percent" Text="SP%:" runat="server"></asp:Label>
                                                <br />
                                                <asp:Label ID="labselling_Price" Text="SP:" runat="server"></asp:Label>

                                                <br />
                                                <asp:HiddenField ID="hd_nid" runat="server" />
                                                <asp:CheckBox ID="ckbox_pro" runat="server" AutoPostBack="true" OnCheckedChanged="ckbox_click" Visible="false" />
                                            </ItemTemplate>
                                        </asp:TemplateField>
                                        <asp:TemplateField HeaderText="Percent %" Visible="false">
                                            <ItemTemplate>
                                                <asp:TextBox ID="txtpercent" ReadOnly="false" runat="server"
                                                    Text='<%#Eval("percent") %>' CssClass="form-control" Width="100"
                                                    AutoPostBack="true" OnTextChanged="txtpercent_TextChanged"
                                                    onkeyup="debouncePostBack(this.id);" />

                                            </ItemTemplate>
                                        </asp:TemplateField>--%>
                                        <asp:TemplateField HeaderText="Price">
                                            <ItemTemplate>
                                                <asp:HiddenField ID="hdnprice" runat="server" Value='<%# Eval("price") %>' />
                                                <asp:TextBox ID="txtprice" ReadOnly="true" runat="server"
                                                    Text='<%# "Unit Price - " + Eval("price") %>'
                                                    CssClass="form-control" Width="150" />

                                                <asp:TextBox ID="txttotalprice" ReadOnly="true" runat="server" Visible="false"
                                                    Text='<%# "Total Price - " + Eval("totalprice") %>'
                                                    CssClass="form-control" Width="150" />
                                            </ItemTemplate>
                                        </asp:TemplateField>

                                        <asp:TemplateField HeaderText="Quantity">
                                            <ItemTemplate>
                                                <%--                                                <asp:TextBox ID="txtqauntity" runat="server" Text='<%#Eval("quantity") %>' CssClass="form-control" Width="100" AutoPostBack="true" OnTextChanged="txtPriceOrQty_TextChanged" />--%>
                                                <asp:TextBox ID="txtqauntity" runat="server"
                                                    Text='<%#Eval("quantity") %>'
                                                    CssClass="form-control"
                                                    Width="100"
                                                    AutoPostBack="true" TextMode="Number" ReadOnly="true"
                                                    OnTextChanged="txtPriceOrQty_TextChanged"
                                                    onkeyup="debouncePostBack(this.id);" />


                                            </ItemTemplate>
                                        </asp:TemplateField>
                                        <asp:TemplateField HeaderText="Action">
                                            <ItemTemplate>

                                                <asp:LinkButton ID="lnkaddproduct" runat="server"
                                                    CssClass="btn btn-success"
                                                    CommandName="add_product"
                                                    CommandArgument="0"
                                                    Text="+">
                                                </asp:LinkButton>

                                                <asp:LinkButton ID="lnkremoveproduct" runat="server"
                                                    CssClass="btn btn-danger"
                                                    CommandName="remove_product"
                                                    CommandArgument='<%# Eval("rowid") %>'
                                                    Text="-">
                                                </asp:LinkButton>
                                                <%--      <asp:LinkButton ID="lnkaddproduct" CssClass="btn btn-success" runat="server" CommandName="add_product" CommandArgument='0'>+</asp:LinkButton>
                                                <asp:LinkButton ID="lnkremoveproduct" CssClass="btn btn-danger" runat="server" CommandName="remove_product" CommandArgument='<%#Eval("rowid") %>'>-</asp:LinkButton>
                                                --%>
                                                <asp:HiddenField ID="hidrowid" runat="server" Value='<%#Eval("rowid") %>' />
                                                <asp:HiddenField ID="hidnid" runat="server" Value='<%#Eval("nid") %>' />
                                                <asp:HiddenField ID="hd_assign_id" runat="server" Value='<%#Eval("assign_id") %>' />
                                            </ItemTemplate>
                                        </asp:TemplateField>


                                    </Columns>


                                </asp:GridView>
                            </div>

                            <div class="col-md-4 form-group" style="padding-top: 25px;">
                                <label>Total Quantity</label>
                                <asp:TextBox ID="txttotqauntity" ReadOnly="true" runat="server" CssClass="form-control"></asp:TextBox>
                            </div>
                            <div class="col-md-4 form-group" style="padding-top: 25px;">
                                <label>Total Price</label>

                                <asp:TextBox ID="txttotprice" runat="server" ReadOnly="true" CssClass="form-control"></asp:TextBox>
                            </div>


                            <%--   <div class="col-md-12 form-group">
                                <label>Status</label>
                                <asp:RadioButton ID="rdActive" runat="server" GroupName="status" Text="Active" />
                                <asp:RadioButton ID="rdInactive" runat="server" GroupName="status" Text="Inactive" />
                            </div>--%>
                        </div>
                        <div class="col-md-12">
                          <asp:Button ID="btnSave" runat="server" CssClass="btn btn_add" Text="Save"
    OnClientClick="collectTableData(); showSyncLoader(60);"
    OnClick="btnSave_Click" />
                            <asp:LinkButton ID="btncancel" runat="server" CssClass="btn btn_cancel" OnClick="btnBack_Click">CANCEL</asp:LinkButton>

                        </div>
                    </fieldset>
                </div>
            </asp:View>
        </asp:MultiView>
    </div>
</asp:Content>
<asp:Content ID="Content3" ContentPlaceHolderID="footerScript" runat="Server">
    <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>

    <!-- DateTimePicker JS -->
    <script src="https://cdn.jsdelivr.net/npm/jquery-datetimepicker@2.5.20/build/jquery.datetimepicker.full.min.js"></script>

    <!-- Select2 JS -->
    <script src="https://cdn.jsdelivr.net/npm/select2@4.1.0-rc.0/dist/js/select2.min.js"></script>

    <!-- Overlay -->
    <div id="otherbarcodebg" class="overlay-bg" onclick="closebarcodepopup();" style="display: none;"></div>

    <!-- Popup -->
    <div id="divaddnewbarcode" class="newpopupsalarydiv" style="display: none; width: 900px;">
        <!-- Close Button -->
        <div class="text-right">
            <img src="images/cancel.png" onclick="closebarcodepopup();" width="20" style="cursor: pointer;" />
        </div>

        <div class="container-fluid py-3" id="divbarcode" runat="server">
            <fieldset class="fieldset border p-3">
                <legend class="w-auto">Select BarCode</legend>

                <div class="row">
                    <div class="form-group col-md-4">
                        <label>Category</label>
                        <asp:TextBox runat="server" ID="txtcategory" CssClass="form-control" ReadOnly="true" Placeholder="Category"></asp:TextBox>
                    </div>
                    <div class="form-group col-md-4">
                        <label>Sub Category</label>
                        <asp:TextBox runat="server" ID="txtsubcategory" CssClass="form-control" ReadOnly="true" Placeholder="Sub Category"></asp:TextBox>
                    </div>
                    <div class="form-group col-md-4">
                        <label>Product Name</label>
                        <asp:TextBox runat="server" ID="txtproduct" CssClass="form-control" ReadOnly="true" Placeholder="Product Name"></asp:TextBox>
                    </div>
                </div>

                <!-- Grid -->
                <div class="row">
                    <div class="col-md-12">
                        <asp:GridView ID="GridView1" runat="server" Width="100%"
                            AutoGenerateColumns="False"
                            GridLines="Both"
                            CellPadding="5"
                            BackColor="White"
                            BorderColor="#999999"
                            BorderStyle="Solid"
                            BorderWidth="1px"
                            CellSpacing="1"
                            RowStyle-HorizontalAlign="Center"
                            ShowHeader="true"
                            DataKeyNames="nid"
                            ShowFooter="true"
                            AllowPaging="False"
                            ClientIDMode="Static"
                            OnRowDataBound="GridView1_RowDataBound">

                            <Columns>


                                <asp:TemplateField HeaderText="SNo">
                                    <ItemTemplate>
                                        <%# Container.DataItemIndex + 1 %>
                                    </ItemTemplate>
                                </asp:TemplateField>

                                <asp:TemplateField HeaderText="Product Barcode">
                                    <ItemTemplate>
                                        <asp:Label ID="labbarcode_number" runat="server"
                                            Text='<%# Eval("barcode_number") %>' />
                                    </ItemTemplate>
                                </asp:TemplateField>


                                <asp:BoundField DataField="barcode_number" Visible="false" />

                                <asp:TemplateField HeaderText="Select For Assign">
                                    <HeaderTemplate>
                                        <asp:Label runat="server" Text="Select For Assign " />
                                        <asp:CheckBox ID="chkSelectAll" runat="server"
                                            onclick="toggleSelectAll(this);" />
                                    </HeaderTemplate>

                                    <ItemTemplate>
                                        <asp:CheckBox ID="chkEditRec" runat="server"
                                            ToolTip='<%# Eval("nid") %>' />
                                    </ItemTemplate>
                                </asp:TemplateField>

                            </Columns>
                        </asp:GridView>

                    </div>
                </div>

                <!-- Pager goes here -->
                <div id="pager" class="text-center mt-3"></div>

                <div class="text-center mt-3">
                    <asp:LinkButton ID="btnsubmit" runat="server" CssClass="btn_send btn_rad"
                        OnClick="btnsubmit_Click" ValidationGroup="rrts">
                        Assign Product</asp:LinkButton>
                </div>

            </fieldset>
        </div>
        <div class="container-fluid py-3" id="divpaymnet" runat="server">
            <fieldset class="fieldset border p-3">
                <legend class="w-auto">Set Currency Rate</legend>
                <asp:LinkButton ID="LinkButton1" runat="server" CssClass="btn_send btn_rad"
                    OnClick="btnsubmitrate_Click">
Edit Rate</asp:LinkButton>
                <div class="row">
                    <asp:GridView ID="GridView2" Width="80%" runat="server"
                        AutoGenerateColumns="False"
                        CssClass="gridview"
                        AllowPaging="false"
                        DataKeyNames="nid"
                        OnRowCommand="GridView2_RowCommand">

                        <Columns>


                            <asp:TemplateField>
                                <HeaderTemplate>S.No.</HeaderTemplate>
                                <ItemTemplate>
                                    <%# Container.DataItemIndex + 1 %>
                                </ItemTemplate>
                            </asp:TemplateField>


                            <asp:BoundField DataField="name" HeaderText="Currency Name" />


                            <asp:TemplateField HeaderText="Currency Code">
                                <ItemTemplate>
                                    <asp:Label ID="lblCode" runat="server" Text='<%# Eval("code") %>'></asp:Label>
                                </ItemTemplate>
                            </asp:TemplateField>


                            <asp:TemplateField HeaderText="Current Converter Rate">
                                <ItemTemplate>
                                    <asp:Label ID="lblConverterRate"
                                        runat="server"
                                        Text='<%# Eval("converter_rate") %>'>
                                    </asp:Label>
                                </ItemTemplate>
                            </asp:TemplateField>



                            <asp:TemplateField HeaderText="New Rate">
                                <ItemTemplate>
                                    <asp:TextBox ID="txtNewRate" runat="server"
                                        CssClass="form-control"
                                        Width="90px"
                                        TextMode="Number"
                                        step="0.0001"
                                        placeholder="Enter rate"
                                        ReadOnly="true" />
                                </ItemTemplate>
                            </asp:TemplateField>


                            <asp:TemplateField HeaderText="Save">
                                <ItemTemplate>
                                    <asp:Button ID="btnedit" runat="server"
                                        Text="Save"
                                        CssClass="btn_green_a"
                                        CommandName="EditItem"
                                        CommandArgument='<%# Eval("nid") %>'
                                        Enabled="false" />
                                </ItemTemplate>
                            </asp:TemplateField>

                        </Columns>
                    </asp:GridView>




                </div>




                <legend class="w-auto" runat="server" id="legendmetal" visible="false">Set Metal Rate/gm</legend>
                <asp:LinkButton ID="LinkButton5" runat="server" CssClass="btn_send btn_rad"
                    OnClick="btnmetalrate_Click">
Edit Metal Rate</asp:LinkButton>
                <div class="row">
                    <asp:GridView ID="grmetalrate" Width="80%" runat="server"
                        AutoGenerateColumns="False"
                        CssClass="gridview"
                        AllowPaging="false"
                        DataKeyNames="nid"
                        OnRowCommand="GridView3_RowCommand">

                        <Columns>


                            <asp:TemplateField>
                                <HeaderTemplate>S.No.</HeaderTemplate>
                                <ItemTemplate>
                                    <%# Container.DataItemIndex + 1 %>
                                </ItemTemplate>
                            </asp:TemplateField>


                            <asp:BoundField DataField="countryname" HeaderText="Country Name" />


                            <asp:TemplateField HeaderText="Metal Purity">
                                <ItemTemplate>
                                    <asp:HiddenField ID="hndpurity_id" runat="server" Value='<%# Eval("purity_id") %>' />
                                    <asp:Label ID="lblcountry_purity" runat="server" Text='<%# Eval("country_purity") %>'></asp:Label>
                                </ItemTemplate>
                            </asp:TemplateField>


                            <asp:TemplateField HeaderText="Metal Rate">
                                <ItemTemplate>
                                    <asp:Label ID="lblrate"
                                        runat="server"
                                        Text='<%# Eval("rate") %>'>
                                    </asp:Label>
                                </ItemTemplate>
                            </asp:TemplateField>



                            <asp:TemplateField HeaderText="New Rate">
                                <ItemTemplate>
                                    <asp:TextBox ID="txtNewRate" runat="server"
                                        CssClass="form-control"
                                        Width="90px"
                                        TextMode="Number"
                                        step="0.0001"
                                        placeholder="Enter rate"
                                        ReadOnly="true" />
                                </ItemTemplate>
                            </asp:TemplateField>


                            <asp:TemplateField HeaderText="Save">
                                <ItemTemplate>
                                    <asp:Button ID="btnedit" runat="server"
                                        Text="Save"
                                        CssClass="btn_green_a"
                                        CommandName="EditItem"
                                        CommandArgument='<%# Eval("nid") %>'
                                        Enabled="false" />
                                </ItemTemplate>
                            </asp:TemplateField>

                        </Columns>
                    </asp:GridView>




                </div>

                <div class="text-center mt-6">
                    <label>Alive Dicount</label>
                    <asp:TextBox runat="server" ID="txtalvindiscount" CssClass="form-control" Placeholder="0.00"></asp:TextBox>

                    <asp:LinkButton ID="btnapplyalvindiscount" runat="server" CssClass="btn_send btn_rad"
                        OnClick="btnapplyalvindiscount_click">
Apply</asp:LinkButton>
                </div>

                <div class="text-center mt-6">

                    <asp:LinkButton ID="LinkButton4" runat="server" CssClass="btn_send btn_rad"
                        OnClick="btnoldinvoice_Click">
View Old Invoice</asp:LinkButton>
                    <asp:LinkButton ID="LinkButton2" runat="server" CssClass="btn_send btn_rad"
                        OnClick="btncontinuous_Click">
Continuous WithOut Change</asp:LinkButton>
                    <asp:LinkButton ID="LinkButton3" runat="server" CssClass="btn_send btn_rad"
                        OnClick="btnsubmitrate_ClickNEW" Visible="false">
   Generate Invoice</asp:LinkButton>

                </div>

            </fieldset>
        </div>

    </div>

    <script>
        document.addEventListener("DOMContentLoaded", function () {
            let grid = document.getElementById("GridView1");
            if (!grid) return;

            let rows = grid.querySelectorAll("tr");
            let dataRows = Array.from(rows).slice(1); // skip header row

            let pageSize = 30;   // same as original PageSize
            let currentPage = 1;

            function showPage(page) {
                currentPage = page;
                dataRows.forEach((row, i) => {
                    row.style.display = (i >= (page - 1) * pageSize && i < page * pageSize) ? "" : "none";
                });
                renderPager();
            }

            function renderPager() {
                let pager = document.getElementById("pager");
                pager.innerHTML = "";
                let pageCount = Math.ceil(dataRows.length / pageSize);

                for (let i = 1; i <= pageCount; i++) {
                    let btn = document.createElement("button");
                    btn.innerText = i;
                    btn.className = "btn btn-sm " + (i === currentPage ? "btn-primary" : "btn-primary");
                    btn.onclick = () => showPage(i);
                    pager.appendChild(btn);
                }
            }

            if (dataRows.length > 0) {
                showPage(1); // show first page by default
            }
        });
    </script>



    <div id="popupdiv" style="display: none;" onclick="hidepopup();">
    </div>
    <div class="newpopupdiv" id="divmaster_outer" style="left: 0px; top: 0px; display: none; width: 100%; max-width: 1150px;">
        <div class="modal-dialog" style="margin-top: 0px !important; margin-bottom: 0px !important; width: 100% !important;">
            <!-- Modal content-->
            <div class="modal-content">
                <div class="modal-header">
                    <button type="button" class="close" onclick="hidepopup();">
                        &times;</button>
                </div>
                <div class="modal-body">
                    <section class="banner">
                        <iframe id="iframe_master" frameborder="0" style="width: 100%; height: 600px;"></iframe>

                    </section>
                </div>

            </div>
        </div>
    </div>
    <script type="text/javascript">
        var debounceTimer;
        function debouncePostBack(controlId) {
            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(function () {
                __doPostBack(controlId, '');
            }, 1500);
        }

        function filterAssignGrid(term) {
            var grid = document.getElementById('<%= grvAssign.ClientID %>');
            if (!grid) return;
            var rows = grid.querySelectorAll('tbody tr');
            var lc = term.toLowerCase();
            for (var i = 0; i < rows.length; i++) {
                var r = rows[i];
                if (r.querySelector('th')) continue;
                r.style.display = (r.textContent || r.innerText).toLowerCase().indexOf(lc) >= 0 ? '' : 'none';
            }
        }
    </script>


    <script type="text/javascript">

        //function openbarcodePopup(productid) {
        //    open_master("product_barcodelist.aspx?type=add&productid=" + productid);
        //}


        function openSubCategoryPopup() {
            open_master("SubCategoryInfo.aspx?type=add");

        }
        function openProductPopup() {
            open_master("ProductMaster.aspx?type=add");

        }
        function openResellerPopup() {
            open_master("ResellerMaster.aspx?type=add");

        }
        function open_master(url) {

            document.getElementById("divmaster_outer").style.display = "block";
            document.getElementById("popupdiv").style.display = "block";
            document.getElementById("iframe_master").src = url;
            var docwidth = document.body.offsetWidth;
            var balance = (docwidth - 1150) / 2;
            balance = balance - 10;
            if (balance < 0)
                balance = 0;
            document.getElementById("divmaster_outer").style.left = balance + 'px';

            var tops = posTop();

            tops = tops + 50;
            document.getElementById("divmaster_outer").style.top = tops.toString() + 'px';
        }
        function posTop() {
            return window.pageYOffset || document.documentElement.scrollTop || document.body.scrollTop || 0;
        }

        function hidepopup() {
            document.getElementById("divmaster_outer").style.display = "none";
            document.getElementById("popupdiv").style.display = "none";

            __doPostBack('<%= btnRefreshReseller.UniqueID %>', '');
        }
    </script>



    <script type="text/javascript">
        $(function () {
            // Initialize datetimepicker for all 3 fields
            $('#<%= txtDate.ClientID %>, #<%= txtfromdate.ClientID %>, #<%= txttodate.ClientID %>').datetimepicker({
                timepicker: false,
                mask: false,
                format: 'j F Y' // e.g., 5 May 2025
            });
        });

        function chkfields() {
            var dateIds = ['<%= txtDate.ClientID %>', '<%= txtfromdate.ClientID %>', '<%= txttodate.ClientID %>'];
            var allValid = true;

            for (var i = 0; i < dateIds.length; i++) {
                var input = document.getElementById(dateIds[i]).value;

                if (input.trim() === "") {
                    document.getElementById(dateIds[i]).classList.add("tdcolerror");
                    alert("Please enter a valid date.");
                    allValid = false;
                } else if (!validformat(dateIds[i])) {
                    document.getElementById(dateIds[i]).classList.add("tdcolerror");
                    alert("Invalid date format. Use format like 5 May 2025.");
                    allValid = false;
                } else {
                    document.getElementById(dateIds[i]).classList.remove("tdcolerror");
                }
            }

            return allValid;
        }

        function validformat(id) {
            var input = document.getElementById(id).value;
            var regex = /^([1-9]|[12][0-9]|3[01])\s(January|February|March|April|May|June|July|August|September|October|November|December)\s\d{4}$/;

            return regex.test(input);
        }
    </script>

    <script type="text/javascript">
        function toggleSelectAll(masterCheckbox) {
            var grid = document.getElementById("<%= GridView1.ClientID %>");
            if (grid != null) {
                var checkboxes = grid.getElementsByTagName("input");
                for (var i = 0; i < checkboxes.length; i++) {
                    if (checkboxes[i].type == "checkbox" && checkboxes[i] != masterCheckbox) {
                        checkboxes[i].checked = masterCheckbox.checked;
                    }
                }
            }
        }
    </script>
    <script type="text/javascript">
        function closePopupAndOpen(url) {

            // Close popup
            if (typeof closebarcodepopup === "function") {
                closebarcodepopup();
            }

            // Open invoice in new tab
            window.open(url, '_blank');

            // ❌ stop postback
            return false;
        }
    </script>



    <%-- Then your existing Select2 init script (REPLACE the old one) --%>
    <script>
        $(document).ready(function () {

            // Initialize Select2
            $('#drpinvoicenumber').select2({
                placeholder: "Search Invoice Number...",
                allowClear: true,
                width: '100%',
                dropdownAutoWidth: true
            });

            // Fix AutoPostBack with Select2
            $('#drpinvoicenumber').on('select2:select select2:clear', function () {
                var selectedVal = $(this).val() || '';
                // Set value back explicitly
                $('#drpinvoicenumber').val(selectedVal);
                // Force ASP.NET postback
                __doPostBack('<%=drpinvoicenumber.UniqueID %>', '');
            });


            // Initialize Select2
            $('#drpname').select2({
                placeholder: "Search Reseller Name...",
                allowClear: true,
                width: '100%',
                dropdownAutoWidth: true
            });

            // Fix AutoPostBack with Select2
            $('#drpname').on('select2:select select2:clear', function () {
                var selectedVal = $(this).val() || '';
                // Set value back explicitly
                $('#drpname').val(selectedVal);
                // Force ASP.NET postback
                __doPostBack('<%=drpname.UniqueID %>', '');
            });
        });
    </script>
</asp:Content>
