from django.core.exceptions import ValidationError

from enterprise.constants import CONTENT_FILTER_FIELD_TYPES as cftypes


def validate_content_filter_fields(content_filter):
    """
    Validate particular fields (if present) passed in through content_filter are certain types.
    """
    for key, cftype in cftypes.items():
        if key in content_filter.keys():
            if not isinstance(content_filter[key], cftype['type']):
                raise ValidationError(
                    "Content filter '{}' must be of type {}".format(key, cftype['type'])
                )
            if cftype['type'] == list:
                if not all(cftype['subtype'] == type(x) for x in content_filter[key]):
                    raise ValidationError(
                        "Content filter '{}' must contain values of type {}".format(
                            key, cftype['subtype']
                        )
                    )

