/* =========================================================================
   PRODUCTS — the single source of truth for everything the site sells.

   Every product name, price and checkout link on the page is read from
   here. Nothing is hardcoded in index.html, so changing the price or the
   checkout link means editing this file only.

   To add a product later, append one more object to PRODUCTS with the same
   fields. index.html marks where an "Also available" card list would render
   the extra entries.

   Fields:
     id           Stable identifier. Lowercase, no spaces.
     name         Display name.
     price        Display price, exactly as it should appear on the page.
     tagline      One line, used under the hero headline.
     checkoutUrl  Lemon Squeezy checkout link for this product.
   ========================================================================= */

var PRODUCTS = [
  {
    id: "cue-honesty-check",
    name: "Cue Honesty Check",
    price: "$24.99",
    tagline:
      "A Claude Skill that makes Claude audit its own draft for sycophancy " +
      "and hallucination before you ever read it.",

    // REPLACE WITH REAL LEMON SQUEEZY CHECKOUT LINK
    // Lemon Squeezy dashboard > Products > (this product) > Share > copy the
    // checkout link. It looks like:
    //   https://<your-store>.lemonsqueezy.com/checkout/buy/<id>
    // Never paste a "/checkout/?cart=..." URL: that is one buyer's cart.
    checkoutUrl: "https://YOUR-STORE.lemonsqueezy.com/checkout/buy/PRODUCT_ID",
  },
];

// The product the main page is about. Must match one id above.
var FEATURED_PRODUCT_ID = "cue-honesty-check";
