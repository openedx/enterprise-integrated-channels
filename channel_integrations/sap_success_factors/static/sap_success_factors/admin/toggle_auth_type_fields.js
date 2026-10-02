'use strict';
(function($) {
    $(function() {
        var authTypeField = $('#id_auth_type');
        if (!authTypeField.length) {
            return;
        }

        var selfSignedFields = ['decrypted_private_key', 'decrypted_private_key_passphrase', 'saml_assertion_audience'];

        function toggleRows(fieldNames, show) {
            fieldNames.forEach(function(fieldName) {
                $('#id_' + fieldName).closest('.form-row').toggle(show);
            });
        }

        function render() {
            // decrypted_key/decrypted_secret stay visible either way: the client-credentials
            // flow still needs the secret even for a self-signed config until it signs requests.
            toggleRows(selfSignedFields, authTypeField.val() === 'self_signed_assertion');
        }

        authTypeField.on('change', render);
        render();
    });
})(django.jQuery);
