'use strict';
(function($) {
    $(function() {
        var authTypeField = $('#id_auth_type');
        if (!authTypeField.length) {
            return;
        }

        var selfSignedFields = [
            'decrypted_private_key', 'decrypted_private_key_passphrase', 'saml_assertion_audience', 'sapsf_api_server_url'
        ];
        var sapSignedFields = ['decrypted_secret'];

        function toggleRows(fieldNames, show) {
            fieldNames.forEach(function(fieldName) {
                var row = $('#id_' + fieldName).closest('.form-row');
                // Keep a field with a validation error visible.
                row.toggle(show || row.hasClass('errors'));
            });
        }

        function render() {
            // The client ID (decrypted_key) is used by both auth types, so it is never hidden.
            var isSelfSigned = authTypeField.val() === 'self_signed_assertion';
            toggleRows(selfSignedFields, isSelfSigned);
            toggleRows(sapSignedFields, !isSelfSigned);
        }

        authTypeField.on('change', render);
        render();
    });
})(django.jQuery);
