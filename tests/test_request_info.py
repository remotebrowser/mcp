from getgather.request_info import RequestInfo, request_info


class TestRequestInfo:
    def test_empty_request_info(self):
        info = RequestInfo()
        assert info.proxy_type is None

    def test_request_info_with_proxy_type(self):
        info = RequestInfo(proxy_type="proxy-0")
        assert info.proxy_type == "proxy-0"


class TestRequestInfoContextVar:
    def test_context_var_default_is_none(self):
        assert request_info.get() is None

    def test_context_var_can_be_set_and_retrieved(self):
        info = RequestInfo(proxy_type="proxy-0")
        token = request_info.set(info)
        assert request_info.get() is info
        request_info.reset(token)
        assert request_info.get() is None
