from typing import Any, NotRequired, TypedDict

from getgather.mcp.dpage import remote_zen_dpage_mcp_tool
from getgather.mcp.registry import GatherMCP
from getgather.zen_distill import short_lived_mcp_tool


class ToolConfig(TypedDict):
    function_name: str
    description: str
    result_key: str
    url: NotRequired[str]
    timeout: NotRequired[int]
    short_lived: NotRequired[bool]
    pattern_wildcard: NotRequired[str]
    hostname: NotRequired[str]


class McpConfig(TypedDict):
    id: str
    name: str
    tools: list[ToolConfig]


DECLARATIVE_MCP_CONFIG: list[McpConfig] = [
    {
        "id": "adidas",
        "name": "Adidas MCP",
        "tools": [
            {
                "function_name": "get_order_history",
                "description": "Get order history of a adidas.",
                "url": "https://www.adidas.com/us/my-account/order-history",
                "result_key": "adidas_order_history",
            }
        ],
    },
    {
        "id": "agoda",
        "name": "Agoda MCP",
        "tools": [
            {
                "function_name": "get_complete_bookings",
                "description": "Get complete bookings of agoda.",
                "url": "https://www.agoda.com/account/bookings.html?sort=BookingStartDate&state=Completed&page=1",
                "result_key": "agoda_complete_bookings",
            }
        ],
    },
    {
        "id": "aliexpress",
        "name": "AliExpress MCP",
        "tools": [
            {
                "function_name": "get_orders",
                "description": "Get orders of aliexpress.",
                "url": "https://www.aliexpress.com/p/order/index.html",
                "result_key": "aliexpress_orders",
            }
        ],
    },
    {
        "id": "alltrails",
        "name": "Alltrails MCP",
        "tools": [
            {
                "function_name": "get_feed",
                "description": "Get feed of alltrails.",
                "url": "https://www.alltrails.com/my/profile/",
                "result_key": "alltrails_feed",
                "timeout": 10,
            }
        ],
    },
    {
        "id": "amain",
        "name": "Amain Hobbies MCP",
        "tools": [
            {
                "function_name": "get_cart",
                "description": "Get the list of items in the cart from Amain Hobbies",
                "url": "https://www.amainhobbies.com/cart",
                "result_key": "amain_cart",
            }
        ],
    },
    {
        "id": "ashley",
        "name": "Ashley MCP",
        "tools": [
            {
                "function_name": "get_cart",
                "description": "Get the list of items in the cart from Ashley",
                "url": "https://www.ashleyfurniture.com/cart/",
                "result_key": "ashley_cart",
            }
        ],
    },
    {
        "id": "audible",
        "name": "Audible MCP",
        "tools": [
            {
                "function_name": "get_book_list",
                "description": "Get book list from Audible.com.",
                "url": "https://www.audible.com/library/titles",
                "result_key": "audible_book_list",
            },
            {
                "function_name": "get_wishlist",
                "description": "Get wishlist from Audible.",
                "url": "https://www.audible.com/library/wishlist",
                "result_key": "audible_wishlist",
            },
        ],
    },
    {
        "id": "bbc",
        "name": "BBC MCP",
        "tools": [
            {
                "function_name": "get_saved_articles",
                "description": "Get the list of saved articles from BBC news site",
                "url": "https://www.bbc.com/saved",
                "result_key": "saved_articles",
            }
        ],
    },
    {
        "id": "bedbathandbeyond",
        "name": "Bed Bath & Beyond MCP",
        "tools": [
            {
                "function_name": "get_cart",
                "description": "Get the list of items in the cart from Bed Bath & Beyond",
                "url": "https://www.bedbathandbeyond.com/cart",
                "result_key": "bedbathandbeyond_cart",
            }
        ],
    },
    {
        "id": "booking",
        "name": "Booking MCP",
        "tools": [
            {
                "function_name": "get_past_trips",
                "description": "Get past trip of booking.com.",
                "url": "https://secure.booking.com/mytrips.html",
                "result_key": "booking_past_trips",
            }
        ],
    },
    {
        "id": "chewy",
        "name": "Chewy MCP",
        "tools": [
            {
                "function_name": "get_orders",
                "description": "Get the list of orders from Chewy",
                "url": "https://www.chewy.com/app/account/orderhistory",
                "result_key": "chewy_orders",
            }
        ],
    },
    {
        "id": "cnn",
        "name": "CNN MCP",
        "tools": [
            {
                "function_name": "get_latest_stories",
                "description": "Get the latest stories from CNN.",
                "url": "https://lite.cnn.com",
                "pattern_wildcard": "**/cnn-*.html",
                "result_key": "stories",
                "hostname": "cnn.com",
                "short_lived": True,
            }
        ],
    },
    {
        "id": "containerstore",
        "name": "Container Store MCP",
        "tools": [
            {
                "function_name": "get_orders",
                "description": "Get the list of orders from Container Store",
                "url": "https://www.containerstore.com/orders",
                "result_key": "containerstore_orders",
            }
        ],
    },
    {
        "id": "delta",
        "name": "Delta MCP",
        "tools": [
            {
                "function_name": "get_trips",
                "description": "Get trips of delta.",
                "url": "https://www.delta.com/mytrips",
                "result_key": "delta_trips",
            }
        ],
    },
    {
        "id": "ebay",
        "name": "Ebay MCP",
        "tools": [
            {
                "function_name": "get_cart",
                "description": "Get the list of items in the cart from Ebay",
                "url": "https://cart.ebay.com/",
                "result_key": "ebay_cart",
            }
        ],
    },
    {
        "id": "espn",
        "name": "ESPN MCP",
        "tools": [
            {
                "function_name": "get_schedule",
                "description": "Get the week's college football schedule from ESPN.",
                "url": "https://www.espn.com/college-football/schedule",
                "pattern_wildcard": "**/espn-*.html",
                "result_key": "college_football_schedule",
                "hostname": "espn.com",
                "short_lived": True,
            }
        ],
    },
    {
        "id": "expedia",
        "name": "Expedia MCP",
        "tools": [
            {
                "function_name": "get_past_trips",
                "description": "Get past trips of expedia.",
                "url": "https://www.expedia.com/mytrips",
                "result_key": "expedia_past_trips",
            }
        ],
    },
    {
        "id": "gofood",
        "name": "Gofood MCP",
        "tools": [
            {
                "function_name": "get_purchase_history",
                "description": "Get gofood purchase history.",
                "url": "https://gofood.co.id/en/orders",
                "result_key": "gofood_purchase_history",
                "timeout": 15,
            }
        ],
    },
    {
        "id": "google",
        "name": "Google MCP",
        "tools": [
            {
                "function_name": "get_activity",
                "description": "Get the list of activity from Google",
                "url": "https://myactivity.google.com/myactivity",
                "result_key": "google_activity",
            }
        ],
    },
    {
        "id": "groundnews",
        "name": "Ground News MCP",
        "tools": [
            {
                "function_name": "get_stories",
                "description": "Get the latest news stories from Ground News.",
                "url": "https://ground.news",
                "pattern_wildcard": "**/groundnews-*.html",
                "result_key": "stories",
                "hostname": "ground.news",
                "short_lived": True,
            }
        ],
    },
    {
        "id": "hardcover",
        "name": "Hardcover MCP",
        "tools": [
            {
                "function_name": "get_book_list",
                "description": "Get book list from Hardcover.app.",
                "url": "https://hardcover.app",
                "result_key": "hardcover_book_list",
            }
        ],
    },
    {
        "id": "harrys",
        "name": "Harrys MCP",
        "tools": [
            {
                "function_name": "get_orders",
                "description": "Get the list of orders from Harrys",
                "url": "https://www.harrys.com/en/profile/orders",
                "result_key": "harrys_orders",
            }
        ],
    },
    {
        "id": "hilton",
        "name": "Hilton MCP",
        "tools": [
            {
                "function_name": "get_trips",
                "description": "Get trips of hilton.",
                "url": "https://www.hilton.com/en/hilton-honors/my-trips/",
                "result_key": "hilton_trips",
            }
        ],
    },
    {
        "id": "horizonhobby",
        "name": "Horizon Hobby MCP",
        "tools": [
            {
                "function_name": "get_cart",
                "description": "Get the list of cart from Horizon Hobby",
                "url": "https://www.horizonhobby.com/cart",
                "result_key": "horizonhobby_cart",
            }
        ],
    },
    {
        "id": "ikea",
        "name": "Ikea MCP",
        "tools": [
            {
                "function_name": "get_favorites",
                "description": "Get the list of favorites from Ikea",
                "url": "https://www.ikea.com/us/en/favorites/",
                "result_key": "ikea_favorites",
            }
        ],
    },
    {
        "id": "jetblue",
        "name": "JetBlue MCP",
        "tools": [
            {
                "function_name": "get_profile",
                "description": "Get profile of jetblue.",
                "url": "https://www.jetblue.com/",
                "result_key": "jetblue_profile",
            }
        ],
    },
    {
        "id": "kindle",
        "name": "Kindle MCP",
        "tools": [
            {
                "function_name": "get_book_list",
                "description": "Get book list from Amazon Kindle.",
                "url": "https://www.amazon.com/hz/mycd/digital-console/contentlist/booksAll/dateDsc/",
                "result_key": "kindle_book_list",
            }
        ],
    },
    {
        "id": "lazada",
        "name": "Lazada MCP",
        "tools": [
            {
                "function_name": "get_orders",
                "description": "Get orders of lazada.",
                "url": "https://my.lazada.co.id/customer/order/index/",
                "result_key": "lazada_orders",
            }
        ],
    },
    {
        "id": "lenspure",
        "name": "LensPure MCP",
        "tools": [
            {
                "function_name": "get_cart",
                "description": "Get the list of items in the cart from LensPure",
                "url": "https://www.lenspure.com/cart",
                "result_key": "lenspure_cart",
            }
        ],
    },
    {
        "id": "linkedin",
        "name": "LinkedIn MCP",
        "tools": [
            {
                "function_name": "get_profile",
                "description": "Get profile of linkedin.",
                "url": "https://www.linkedin.com/in/me/",
                "result_key": "linkedin_profile",
            }
        ],
    },
    {
        "id": "lululemon",
        "name": "Lululemon MCP",
        "tools": [
            {
                "function_name": "get_cart",
                "description": "Get the list of items in the cart from Lululemon",
                "url": "https://shop.lululemon.com/cart",
                "result_key": "lululemon_cart",
            }
        ],
    },
    {
        "id": "marriott",
        "name": "Marriott MCP",
        "tools": [
            {
                "function_name": "get_trips",
                "description": "Get trips of marriott.",
                "url": "https://www.marriott.com/loyalty/myReservations.mi",
                "result_key": "marriott_trips",
            }
        ],
    },
    {
        "id": "netflix",
        "name": "Netflix MCP",
        "tools": [
            {
                "function_name": "get_viewing_activity",
                "description": "Get viewing activity of Netflix.",
                "url": "https://www.netflix.com/viewingactivity",
                "result_key": "netflix_viewing_activity",
                "timeout": 10,
            }
        ],
    },
    {
        "id": "nike",
        "name": "Nike MCP",
        "tools": [
            {
                "function_name": "get_orders",
                "description": "Get orders of nike.",
                "url": "https://www.nike.com/orders",
                "result_key": "nike_orders",
            }
        ],
    },
    {
        "id": "npr",
        "name": "NPR MCP",
        "tools": [
            {
                "function_name": "get_headlines",
                "description": "Get the current news headlines from NPR.",
                "url": "https://text.npr.org",
                "pattern_wildcard": "**/npr-*.html",
                "result_key": "headlines",
                "hostname": "npr.org",
                "short_lived": True,
            }
        ],
    },
    {
        "id": "nytimes",
        "name": "NYTimes MCP",
        "tools": [
            {
                "function_name": "get_bestsellers_list",
                "description": "Get the bestsellers list from NY Times.",
                "url": "https://www.nytimes.com/books/best-sellers/",
                "pattern_wildcard": "**/nytimes-*.html",
                "result_key": "best_sellers",
                "hostname": "nytimes.com",
                "short_lived": True,
            }
        ],
    },
    {
        "id": "petsmart",
        "name": "Petsmart MCP",
        "tools": [
            {
                "function_name": "get_cart",
                "description": "Get the list of items in the cart from Petsmart",
                "url": "https://www.petsmart.com/cart",
                "result_key": "petsmart_cart",
            }
        ],
    },
    {
        "id": "quince",
        "name": "Quince MCP",
        "tools": [
            {
                "function_name": "get_orders",
                "description": "Get orders of quince.",
                "url": "https://www.quince.com/orders",
                "result_key": "quince_orders",
            }
        ],
    },
    {
        "id": "revolve",
        "name": "Revolve MCP",
        "tools": [
            {
                "function_name": "get_orders",
                "description": "Get orders of revolve.",
                "url": "https://www.revolve.com/orders",
                "result_key": "revolve_orders",
            }
        ],
    },
    {
        "id": "seatgeek",
        "name": "Seatgeek MCP",
        "tools": [
            {
                "function_name": "get_tickets",
                "description": "Get tickets of seatgeek.",
                "url": "https://seatgeek.com/tickets",
                "result_key": "seatgeek_tickets",
            }
        ],
    },
    {
        "id": "sephora",
        "name": "Sephora MCP",
        "tools": [
            {
                "function_name": "get_cart",
                "description": "Get the list of items in the cart from Sephora",
                "url": "https://www.sephora.com/cart",
                "result_key": "sephora_cart",
            }
        ],
    },
    {
        "id": "shadestore",
        "name": "Shadestore MCP",
        "tools": [
            {
                "function_name": "get_orders",
                "description": "Get orders of shadestore.",
                "url": "https://www.shadestore.com/orders",
                "result_key": "shadestore_orders",
            }
        ],
    },
    {
        "id": "shein",
        "name": "Shein MCP",
        "tools": [
            {
                "function_name": "get_orders",
                "description": "Get orders of shein.",
                "url": "https://us.shein.com/my/orders.html",
                "result_key": "shein_orders",
            }
        ],
    },
    {
        "id": "starbucks",
        "name": "Starbucks MCP",
        "tools": [
            {
                "function_name": "get_rewards",
                "description": "Get rewards of starbucks.",
                "url": "https://www.starbucks.com/account/rewards",
                "result_key": "starbucks_rewards",
            }
        ],
    },
    {
        "id": "thriftbooks",
        "name": "Thriftbooks MCP",
        "tools": [
            {
                "function_name": "get_cart",
                "description": "Get the list of items in the cart from Thriftbooks",
                "url": "https://www.thriftbooks.com/cart",
                "result_key": "thriftbooks_cart",
            }
        ],
    },
    {
        "id": "traveloka",
        "name": "Traveloka MCP",
        "tools": [
            {
                "function_name": "get_saved_list",
                "description": "Get the saved list from Traveloka",
                "url": "https://www.traveloka.com/en-id/user/saved/list",
                "result_key": "traveloka_saved_list",
            }
        ],
    },
    {
        "id": "zillow",
        "name": "Zillow MCP",
        "tools": [
            {
                "function_name": "get_favorites",
                "description": "Get favorites of zillow.",
                "url": "https://www.zillow.com/myzillow/favorites/",
                "result_key": "zillow_favorites",
            }
        ],
    },
]


def create_declarative_mcp_tools() -> None:
    """Create and register MCP tools from configuration array.

    This function generates GatherMCP instances and their tools dynamically
    from the DECLARATIVE_MCP_CONFIG array. Tools can be either remote zen dpage tools
    or short-lived tools.
    """

    for config in DECLARATIVE_MCP_CONFIG:
        id: str = config["id"]
        name: str = config["name"]

        gather_mcp = GatherMCP(brand_id=id, name=name)

        for tool_config in config["tools"]:
            function_name: str = tool_config["function_name"]
            description: str = tool_config["description"]
            short_lived: bool = tool_config.get("short_lived", False)

            if short_lived:
                url: str = tool_config.get("url", "")
                pattern_wildcard: str = tool_config.get("pattern_wildcard", "")
                result_key: str = tool_config.get("result_key", "")
                hostname: str = tool_config.get("hostname", "")

                def make_short_lived_tool_fn(
                    url: str = url,
                    pattern_wildcard: str = pattern_wildcard,
                    result_key: str = result_key,
                    hostname: str = hostname,
                ):
                    async def tool_func() -> dict[str, Any]:
                        terminated, result = await short_lived_mcp_tool(
                            location=url,
                            pattern_wildcard=pattern_wildcard,
                            result_key=result_key,
                            url_hostname=hostname,
                        )
                        if not terminated:
                            raise ValueError(f"Failed to retrieve {result_key}")
                        return result

                    return tool_func

                tool_func = make_short_lived_tool_fn()

            else:
                url: str = tool_config.get("url", "")
                result_key: str = tool_config.get("result_key", "")
                timeout: int = tool_config.get("timeout", 2)

                def make_remote_tool_fn(
                    url: str = url,
                    result_key: str = result_key,
                    timeout: int = timeout,
                ):
                    async def tool_func() -> dict[str, Any]:
                        return await remote_zen_dpage_mcp_tool(url, result_key, timeout=timeout)

                    return tool_func

                tool_func = make_remote_tool_fn()

            tool_func.__name__ = function_name
            tool_func.__doc__ = description
            gather_mcp.tool(tool_func)
