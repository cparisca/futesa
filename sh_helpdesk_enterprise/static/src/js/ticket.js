$(document).ready(function (e) {
    $(function () {
        $('#portal_assign_multi_user').multiselect();
    });
    $(document).on("change", "#portal_file", function (e) {
        for (var x in this.files) {
            if (this.files[x].size / 1024 > $('#sh_file_size').val()) {

                alert(this.files[x].name + " exceeds the " + String($('#sh_file_size').val()) + "KB file size limit");
                $("#portal_file").val("");
            }
        }
    });
    $("#new_request").click(function () {
        $("#createticketModal").modal("show");
    });
    $.ajax({
        url: "/portal-subcategory-data",
        data: { category_id: $("#portal_category").val() },
        type: "post",
        cache: false,
        success: function (result) {
            var datas = JSON.parse(result);
            $("#portal_subcategory > option").remove();
            $("#portal_subcategory").append('<option value="' + "sub_category" + '">' + "Select Sub Category" + "</option>");
            _.each(datas.sub_categories, function (data) {
                $("#portal_subcategory").append('<option value="' + data.id + '">' + data.name + "</option>");
            });
        },
    });

    $.ajax({
        url: "/portal-partner-data",
        data: {},
        type: "post",
        async: false,
        cache: false,
        success: function (result) {
            var datas = JSON.parse(result);
            $("#partner_ids > option").remove();
            _.each(datas.partners, function (data) {
                $("#partner_ids").append('<option data-id="' + data.id + '" value="' + data.name + '">');
            });
        },
    });
    $(document).on("change", "#partner", function (e) {
        var option = $("#partner_ids").find("[value='" + $("#partner").val() + "']");
        var partner = option.data("id");
        $("#partner_id").val("");
        $("#partner_id").val(partner);
        if ($("#partner_id").val() != "") {
            $.ajax({
                url: "/selected-partner-data",
                data: { partner_id: $("#partner_id").val() },
                type: "post",
                cache: false,
                success: function (result) {
                    var datas = JSON.parse(result);
                    $("#portal_contact_name").val(datas.name);
                    $("#portal_email").val(datas.email);
                },
            });
        } else {
            $("#portal_contact_name").val("");
            $("#portal_email").val("");
        }
    });
    $.ajax({
        url: "/portal-subcategory-data",
        data: { category_id: $("#portal_category").val() },
        type: "post",
        cache: false,
        success: function (result) {
            var datas = JSON.parse(result);
            $("#portal_subcategory > option").remove();
            $("#portal_subcategory").append('<option value="' + "sub_category" + '">' + "Select Sub Category" + "</option>");
            _.each(datas.sub_categories, function (data) {
                $("#portal_subcategory").append('<option value="' + data.id + '">' + data.name + "</option>");
            });
        },
    });
    $.ajax({
        url: "/portal-user-data",
        data: { team_id: $("#portal_team").val() },
        type: "post",
        cache: false,
        success: function (result) {
            var datas = JSON.parse(result);
            $("#portal_assign_user > option").remove();
            $("#portal_assign_user").append('<option value="' + "user" + '">' + "Select Assign User" + "</option>");
            $("#portal_assign_multi_user").multiselect('destroy');
            $("#portal_assign_multi_user > option").remove();
            $("#portal_assign_multi_user").append('<option value="' + "users" + '">' + "Select Multi Users" + "</option>");
            _.each(datas.users, function (data) {
                $("#portal_assign_user").append('<option value="' + data.id + '">' + data.name + "</option>");
                $("#portal_assign_multi_user").append('<option value="' + data.id + '">' + data.name + "</option>");
            });
            $("#portal_assign_multi_user").multiselect();
        },
    });
    $(document).on("change", "#portal_category", function (e) {
        $.ajax({
            url: "/portal-subcategory-data",
            data: { category_id: $("#portal_category").val() },
            type: "post",
            cache: false,
            success: function (result) {
                var datas = JSON.parse(result);
                $("#portal_subcategory > option").remove();
                $("#portal_subcategory").append('<option value="' + "sub_category" + '">' + "Select Sub Category" + "</option>");
                _.each(datas.sub_categories, function (data) {
                    $("#portal_subcategory").append('<option value="' + data.id + '">' + data.name + "</option>");
                });
            },
        });
    });
    $(document).on("change", "#portal_team", function (e) {
        $.ajax({
            url: "/portal-user-data",
            data: { team_id: $("#portal_team").val() },
            type: "post",
            cache: false,
            success: function (result) {
                var datas = JSON.parse(result);
                $("#portal_assign_user > option").remove();
                $("#portal_assign_multi_user").multiselect('destroy');
                $("#portal_assign_multi_user > option").remove();
                $("#portal_assign_user").append('<option value="' + "user" + '">' + "Select Assign User" + "</option>");
                $("#portal_assign_multi_user").append('<option value="' + "users" + '">' + "Select Multi Users" + "</option>");
                _.each(datas.users, function (data) {
                    $("#portal_assign_user").append('<option value="' + data.id + '">' + data.name + "</option>");
                    $("#portal_assign_multi_user").append('<option value="' + data.id + '">' + data.name + "</option>");
                });
                $("#portal_assign_multi_user").multiselect();
            },
        });
    });
});
