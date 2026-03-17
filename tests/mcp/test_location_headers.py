from getgather.mcp.main import parse_location_header


def test_parse_location_header_ignores_missing_and_blank_values():
    assert parse_location_header(None, {}) == {}
    assert parse_location_header("", {}) == {}
    assert parse_location_header("   ", {}) == {}


def test_parse_location_header_accepts_json_object_with_string_values():
    location = (
        '{"city":"San Francisco","state":"CA","country":"US","postal_code":"94103",'
        '"timezone":"America/Los_Angeles"}'
    )

    assert parse_location_header(location, {}) == {
        "city": "San Francisco",
        "state": "CA",
        "country": "US",
        "postal_code": "94103",
        "timezone": "America/Los_Angeles",
    }


def test_parse_location_header_drops_non_string_values():
    location = '{"city":"San Francisco","country":"US","latitude":37.7749,"valid":true}'

    assert parse_location_header(location, {}) == {
        "city": "San Francisco",
        "country": "US",
    }


def test_parse_location_header_rejects_non_object_json():
    assert parse_location_header('"us"', {}) == {}
    assert parse_location_header("[]", {}) == {}
