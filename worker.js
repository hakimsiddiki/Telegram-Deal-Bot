export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    try {
      // ===== KV STORAGE HANDLERS (FREE DB) =====
      if (url.pathname === "/sent_deals") {
        if (request.method === "POST") {
          const body = await request.json();
          const asin = body.asin;
          if (asin) {
            let list = await env.DEALS_KV.get("history") || "[]";
            let history = JSON.parse(list);
            if (!history.includes(asin)) {
              history.push(asin);
              // Keep last 1000 deals to stay within KV limits
              if (history.length > 1000) history.shift();
              await env.DEALS_KV.put("history", JSON.stringify(history));
            }
          }
          return new Response(JSON.stringify({ status: "saved" }), { 
            status: 200, 
            headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" } 
          });
        }
        
        if (request.method === "GET") {
          const list = await env.DEALS_KV.get("history") || "[]";
          return new Response(list, { 
            status: 200, 
            headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" } 
          });
        }
      }

      // ===== TARGET DETECTION =====
      let targetUrl;

      // Telegram API requests
      if (url.pathname.startsWith("/bot")) {
        targetUrl = "https://api.telegram.org" + url.pathname + url.search;
      }

      // Amazon requests (scraper)
      else if (url.searchParams.get("url")) {
        targetUrl = url.searchParams.get("url");
      }

      // Default passthrough
      else {
        return new Response("Bridge Active ✅ | KV Supported", { status: 200 });
      }

      // ===== CLEAN UPSTREAM HEADERS =====
      const headers = new Headers();
      const contentType = request.headers.get("content-type");
      if (contentType) headers.set("content-type", contentType);

      if (targetUrl.includes("api.telegram.org")) {
        headers.set("User-Agent", "TelegramDealBot/1.0");
      } else {
        headers.set(
          "User-Agent",
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/121 Safari/537.36"
        );
        headers.set("Accept-Language", "en-US,en;q=0.9");
        headers.set("Cache-Control", "no-cache");
      }

      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 15000);

      // ===== FORWARD REQUEST =====
      let response;
      try {
        response = await fetch(targetUrl, {
          method: request.method,
          headers: headers,
          body: request.method === "GET" ? null : await request.arrayBuffer(),
          redirect: "follow",
          signal: controller.signal
        });
      } finally {
        clearTimeout(timeoutId);
      }

      const newResponse = new Response(response.body, response);
      newResponse.headers.set("Access-Control-Allow-Origin", "*");
      return newResponse;

    } catch (err) {
      return new Response("Bridge Error: " + err.message, { status: 500 });
    }
  }
};
