// Electro Stock — Remote License Verifier (Cloudflare Worker)
// ==============================================================
// ⚠ DEPRECATED — no longer needed.
//
// License verification switched from a shared HMAC secret to a
// public/private ECDSA keypair. Verification now happens entirely
// in the browser (see LICENSE_PUBLIC_KEY_B64 in
// electro_stock_inventory.html) — no server call at all, local mode
// or GitHub mode or otherwise. If you previously deployed this
// Worker, it's safe to delete it from your Cloudflare dashboard.
// See SECURITY_NOTES.md for the current setup.
// ==============================================================

export default {
  async fetch(request, env) {
    if (request.method === "OPTIONS") {
      return new Response(null, { headers: corsHeaders() });
    }
    if (request.method !== "POST") {
      return jsonResponse({ ok: false, error: "Method not allowed" }, 405);
    }

    let body;
    try {
      body = await request.json();
    } catch (e) {
      return jsonResponse({ ok: false, error: "Invalid JSON body" }, 400);
    }

    const key = (body.key || "").trim();
    const result = await verifyLicenseKey(key, env.LICENSE_SECRET);
    return jsonResponse({ ok: true, valid: result.valid, reason: result.reason, payload: result.payload });
  },
};

function corsHeaders() {
  return {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Content-Type": "application/json",
  };
}

function jsonResponse(obj, status = 200) {
  return new Response(JSON.stringify(obj), { status, headers: corsHeaders() });
}

function b64urlToBytes(b64) {
  let s = b64.replace(/-/g, "+").replace(/_/g, "/");
  while (s.length % 4) s += "=";
  const bin = atob(s);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return bytes;
}

async function hmacSha256Base64(secret, message) {
  const enc = new TextEncoder();
  const cryptoKey = await crypto.subtle.importKey("raw", enc.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const sig = await crypto.subtle.sign("HMAC", cryptoKey, enc.encode(message));
  return btoa(String.fromCharCode(...new Uint8Array(sig)));
}

async function verifyLicenseKey(keyStr, secret) {
  if (!secret) return { valid: false, reason: "Verifier is not configured with a secret yet." };
  if (!keyStr || keyStr.indexOf(".") === -1) return { valid: false, reason: "Malformed license key." };
  const parts = keyStr.trim().split(".");
  if (parts.length !== 2) return { valid: false, reason: "Malformed license key." };
  const [payloadB64, sigB64] = parts;

  let payload;
  try {
    payload = JSON.parse(new TextDecoder("utf-8").decode(b64urlToBytes(payloadB64)));
  } catch (e) {
    return { valid: false, reason: "Could not read license payload." };
  }

  const expectedSig = await hmacSha256Base64(secret, payloadB64);
  if (expectedSig !== sigB64) {
    return { valid: false, reason: "Invalid signature — license was not issued for this system." };
  }

  if (payload.expiry) {
    const exp = new Date(payload.expiry + "T23:59:59");
    if (exp.getTime() < Date.now()) {
      return { valid: false, reason: `License expired on ${payload.expiry}. Contact your provider for renewal.`, payload };
    }
  }

  return { valid: true, payload };
}
