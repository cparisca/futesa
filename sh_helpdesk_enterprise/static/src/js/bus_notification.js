odoo.define('sh_helpdesk_enterprise.notification_manager', function (require) {
    "use strict";
    const { Markup } = require('web.utils');
    var AbstractService = require('web.AbstractService');
    var core = require("web.core");
    var _t = core._t;
    var sh_helpdesk_enterprise_notification_manager = AbstractService.extend({
        dependencies: ['bus_service'],

        /**
         * @override
         */
        start: function () {
            this._super.apply(this, arguments);
            this.call('bus_service', 'onNotification', this, this._onNotification);
        },

        _onNotification: function (notifications) {
            console.log("_onNotification 1");
            for (const { payload, type }
                of notifications) {
                console.log(type)

                if (type === "sh_helpdesk_enterprise_notification_info") {
                    if (payload.message) {

                        console.log("payload.message ==>", payload.message);

                    }

                    payload.message = Markup(payload.message);
                    console.log(payload.message)
                    this.displayNotification({ title: payload.title, message: payload.message, type: 'warning', sticky: true, messageIsHtml: true });
                }
                if (type === "sh_helpdesk_enterprise_notification_danger") {
                    if (payload.message) {

                        console.log("payload.message ==>", payload.message);

                    }

                    this.displayNotification({ title: payload.title, message: payload.message, type: 'danger', sticky: true });
                }
            }
        }

    });

    core.serviceRegistry.add('sh_helpdesk_enterprise_notification_manager', sh_helpdesk_enterprise_notification_manager);

    return sh_helpdesk_enterprise_notification_manager;

});