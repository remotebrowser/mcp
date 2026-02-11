from getgather.request_info import RequestInfo, is_empty_request_info, request_info


class TestRequestInfo:
    def test_empty_request_info(self):
        """Test creating RequestInfo with all defaults."""
        info = RequestInfo()
        assert info.city is None
        assert info.state is None
        assert info.country is None
        assert info.postal_code is None
        assert info.timezone is None
        assert info.proxy_type is None

    def test_full_request_info(self):
        """Test creating RequestInfo with all fields."""
        info = RequestInfo(
            city="San Francisco",
            state="CA",
            country="US",
            postal_code="94102",
            timezone="America/Los_Angeles",
            proxy_type="proxy-0",
        )
        assert info.city == "San Francisco"
        assert info.state == "CA"
        assert info.country == "US"
        assert info.postal_code == "94102"
        assert info.timezone == "America/Los_Angeles"
        assert info.proxy_type == "proxy-0"

    def test_partial_request_info(self):
        """Test creating RequestInfo with some fields."""
        info = RequestInfo(city="New York", country="US")
        assert info.city == "New York"
        assert info.state is None
        assert info.country == "US"
        assert info.postal_code is None
        assert info.timezone is None
        assert info.proxy_type is None

    def test_request_info_serialization(self):
        """Test RequestInfo can be serialized to dict."""
        info = RequestInfo(city="Austin", state="TX", country="US")
        data = info.model_dump()
        assert data == {
            "city": "Austin",
            "state": "TX",
            "country": "US",
            "postal_code": None,
            "timezone": None,
            "proxy_type": None,
        }

    def test_request_info_deserialization(self):
        """Test RequestInfo can be deserialized from dict."""
        data = {
            "city": "Seattle",
            "state": "WA",
            "country": "US",
            "postal_code": "98101",
            "timezone": "America/Los_Angeles",
        }
        info = RequestInfo.model_validate(data)
        assert info.city == "Seattle"
        assert info.state == "WA"
        assert info.country == "US"
        assert info.postal_code == "98101"
        assert info.timezone == "America/Los_Angeles"
        assert info.proxy_type is None


class TestRequestInfoContextVar:
    def test_context_var_default_is_none(self):
        """Test that request_info context var defaults to None."""
        assert request_info.get() is None

    def test_context_var_can_be_set_and_retrieved(self):
        """Test that request_info context var can be set and retrieved."""
        info = RequestInfo(city="Boston", state="MA")
        token = request_info.set(info)
        assert request_info.get() is info
        request_info.reset(token)
        assert request_info.get() is None

    def test_context_var_isolation(self):
        """Test that context var changes don't affect the default."""
        info = RequestInfo(country="CA")
        token = request_info.set(info)
        assert request_info.get() is info
        assert info.country == "CA"
        request_info.reset(token)
        assert request_info.get() is None


def test_is_empty_request_info():
    """Test the is_empty_request_info utility function."""
    empty_info = RequestInfo()
    assert is_empty_request_info(empty_info) is True

    non_empty_info = RequestInfo(city="Miami")
    assert is_empty_request_info(non_empty_info) is False

    all_fields_none = RequestInfo(
        city=None, state=None, country=None, postal_code=None, timezone=None, proxy_type=None
    )
    assert is_empty_request_info(all_fields_none) is True
    different_empty = RequestInfo(
        city=None, state=None, country=None, postal_code=None, timezone=None, proxy_type=""
    )
    assert is_empty_request_info(different_empty) is True
