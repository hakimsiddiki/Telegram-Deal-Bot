import unittest

import app


class AmazonApiParsingTests(unittest.TestCase):
    def test_extract_product_data_from_amazon_api_payload(self):
        payload = {
            "ItemsResult": {
                "Items": [
                    {
                        "ASIN": "B09XYZ1234",
                        "ItemInfo": {
                            "Title": {"DisplayValue": "Test Wireless Earbuds"},
                            "Features": {"DisplayValues": ["Noise cancellation"]}
                        },
                        "Offers": {
                            "Listings": [
                                {
                                    "Price": {
                                        "Amount": 1999,
                                        "Currency": "INR"
                                    },
                                    "SavingBasis": {
                                        "Amount": 500,
                                        "Currency": "INR"
                                    }
                                }
                            ]
                        },
                        "Images": {
                            "Primary": {
                                "Large": {"URL": "https://example.com/earbuds.jpg"}
                            }
                        },
                        "CustomerReviews": {
                            "StarRating": 4.7
                        }
                    }
                ]
            }
        }

        data = app.extract_product_data_from_amazon_api_payload(payload, "B09XYZ1234")

        self.assertEqual(data["title"], "Test Wireless Earbuds")
        self.assertEqual(data["current_price"], "1999")
        self.assertEqual(data["original_price"], "2499")
        self.assertEqual(data["discount_val"], 20)
        self.assertEqual(data["rating"], "4.7")
        self.assertEqual(data["image"], "https://example.com/earbuds.jpg")

    def test_extract_product_data_from_summary_offer_payload(self):
        payload = {
            "items": [
                {
                    "itemInfo": {"title": {"displayValue": "Amazon.in: Rain Jacket"}},
                    "offers": {
                        "summaries": [
                            {
                                "lowestPrice": {"displayAmount": "Rs.799.00"},
                            }
                        ],
                        "listPrice": {"displayAmount": "Rs.1,999.00"},
                    },
                    "images": {
                        "primary": {
                            "medium": {"url": "https://example.com/jacket.jpg"}
                        }
                    },
                }
            ]
        }

        data = app.extract_product_data_from_amazon_api_payload(payload, "B0TEST1234")

        self.assertEqual(data["title"], "Rain Jacket")
        self.assertEqual(data["current_price"], "799")
        self.assertEqual(data["original_price"], "1999")
        self.assertEqual(data["discount_val"], 60)
        self.assertEqual(data["image"], "https://example.com/jacket.jpg")

    def test_extract_product_data_from_offscreen_html_price(self):
        html = """
        <html>
          <h1 id="productTitle">USB Cable</h1>
          <div id="corePriceDisplay_mobile_feature_div">
            <span class="a-price"><span class="a-offscreen">Rs.299.00</span></span>
            <span class="a-price a-text-price"><span class="a-offscreen">Rs.999.00</span></span>
            <span class="savingsPercentage">-70%</span>
          </div>
        </html>
        """
        soup = app.BeautifulSoup(html, "lxml")

        data = app.extract_product_data(soup, "B0HTML1234")

        self.assertEqual(data["current_price"], "299")
        self.assertEqual(data["original_price"], "999")
        self.assertEqual(data["discount_val"], 70)

    def test_extract_listing_card_data(self):
        html = """
        <div id="gridItemRoot">
          <a href="/dp/B0CACHE123">
            <img alt="Cached USB Charger" src="https://example.com/charger.jpg" />
          </a>
          <span class="a-price"><span class="a-offscreen">Rs.399.00</span></span>
          <span class="a-price a-text-price"><span class="a-offscreen">Rs.999.00</span></span>
          <span>60% off</span>
        </div>
        """

        deals = app.extract_listing_card_data(html)

        self.assertEqual(deals["B0CACHE123"]["title"], "Cached USB Charger")
        self.assertEqual(deals["B0CACHE123"]["current_price"], "399")
        self.assertEqual(deals["B0CACHE123"]["original_price"], "999")
        self.assertEqual(deals["B0CACHE123"]["discount_val"], 60)


if __name__ == "__main__":
    unittest.main()
