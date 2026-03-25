# web_tools.py Security Merge Analysis

## Summary
- **Local version**: 2402 lines with Page Storage System (SQLite + FTS5)
- **Upstream version**: 1727 lines with SSRF protection (`is_safe_url`)
- **Key difference**: Local has page storage; upstream has SSRF protection

## Merge Strategy: ADD SSRF protection to local (preserve page storage)

---

## 1. New File Required

### `tools/url_safety.py` (DOES NOT EXIST LOCALLY)
**Action**: Copy from upstream `origin/main:tools/url_safety.py`

This module provides `is_safe_url()` function that:
- Blocks requests to private/internal IP addresses (SSRF protection)
- Blocks cloud metadata endpoints (169.254.169.254, metadata.google.internal)
- Handles CGNAT range (100.64.0.0/10) not covered by `ipaddress.is_private`
- Fails closed on DNS errors

---

## 2. Import Changes (Line ~577)

### Current local imports:
```python
from tools.website_policy import check_website_access
```

### Add new import:
```python
from tools.url_safety import is_safe_url
from tools.website_policy import check_website_access
```

---

## 3. Insertion Points for SSRF Protection

### 3.1 `web_extract_tool` - PRE-FILTER URLs (RECOMMENDED UPSTREAM APPROACH)

**Location**: Lines 1409-1413 (after logger.info, before backend dispatch)

**Current code** (lines 1409-1413):
```python
    try:
        logger.info("Extracting content from %d URL(s)", len(urls))

        # Dispatch to the configured backend
        backend = _get_backend()
```

**Replace WITH** (pre-filter URLs before ANY backend):
```python
    try:
        logger.info("Extracting content from %d URL(s)", len(urls))

        # ── SSRF protection — filter out private/internal URLs before any backend ──
        safe_urls = []
        ssrf_blocked: List[Dict[str, Any]] = []
        for url in urls:
            if not is_safe_url(url):
                ssrf_blocked.append({
                    "url": url, "title": "", "content": "",
                    "error": "Blocked: URL targets a private or internal network address",
                })
            else:
                safe_urls.append(url)

        # Dispatch only safe URLs to the configured backend
        if not safe_urls:
            results = []
        else:
            backend = _get_backend()
```

**Then at line ~1543** (after building response dict), ADD:
```python
        # Merge any SSRF-blocked results back in
        if ssrf_blocked:
            results = ssrf_blocked + results

        response = {"results": results}
```

**NOTE**: This approach requires adjusting all backend paths to use `safe_urls` instead of `urls`:
- Parallel: `results = await _parallel_extract(safe_urls)`
- Tavily: `_tavily_request("extract", {"urls": safe_urls, ...})`
- Firecrawl: `for url in safe_urls:` instead of `for url in urls:`

---

### 3.2 `web_crawl_tool` - Tavily path

**Location**: Lines 1725-1735

**Current code** (lines 1725-1731):
```python
        if backend == "tavily":
            # Ensure URL has protocol
            if not url.startswith(('http://', 'https://')):
                url = f'https://{url}'

            # Website policy check
            blocked = check_website_access(url)
```

**Insert AFTER protocol prefix, BEFORE policy check**:
```python
        if backend == "tavily":
            # Ensure URL has protocol
            if not url.startswith(('http://', 'https://')):
                url = f'https://{url}'

            # SSRF protection — block private/internal addresses
            if not is_safe_url(url):
                return json.dumps({"results": [{"url": url, "title": "", "content": "",
                    "error": "Blocked: URL targets a private or internal network address"}]}, ensure_ascii=False)

            # Website policy check
            blocked = check_website_access(url)
```

---

### 3.3 `web_crawl_tool` - Firecrawl path

**Location**: Lines 1814-1823

**Current code** (lines 1814-1822):
```python
        # Ensure URL has protocol
        if not url.startswith(('http://', 'https://')):
            url = f'https://{url}'
            logger.info("Added https:// prefix to URL: %s", url)
        
        instructions_text = f" with instructions: '{instructions}'" if instructions else ""
        logger.info("Crawling %s%s", url, instructions_text)
        
        # Website policy check — block before crawling
        blocked = check_website_access(url)
```

**Insert AFTER logging, BEFORE policy check**:
```python
        # Ensure URL has protocol
        if not url.startswith(('http://', 'https://')):
            url = f'https://{url}'
            logger.info("Added https:// prefix to URL: %s", url)
        
        instructions_text = f" with instructions: '{instructions}'" if instructions else ""
        logger.info("Crawling %s%s", url, instructions_text)
        
        # SSRF protection — block private/internal addresses
        if not is_safe_url(url):
            return json.dumps({"results": [{"url": url, "title": "", "content": "",
                "error": "Blocked: URL targets a private or internal network address"}]}, ensure_ascii=False)

        # Website policy check — block before crawling
        blocked = check_website_access(url)
```

---

## 4. Summary of Changes

| Location | Change Type | Description |
|----------|-------------|-------------|
| Line ~577 | ADD IMPORT | `from tools.url_safety import is_safe_url` |
| Line ~1409 | INSERT CODE | Pre-filter URLs with SSRF check before backend dispatch |
| Line ~1414 | MODIFY | Wrap backend dispatch in `if safe_urls:` block |
| Line ~1415 | MODIFY | Change `urls` to `safe_urls` in all backend paths |
| Line ~1543 | INSERT CODE | Merge `ssrf_blocked` results back into response |
| Line ~1729 | INSERT CODE | SSRF check in web_crawl_tool Tavily path |
| Line ~1821 | INSERT CODE | SSRF check in web_crawl_tool Firecrawl path |
| New file | CREATE | `tools/url_safety.py` from upstream |

---

## 5. Execution Commands

```bash
# 1. Create the new url_safety.py file
cd ~/Projects/hermes-agent
git show origin/main:tools/url_safety.py > tools/url_safety.py

# 2. Apply patches to web_tools.py (see patches below)
```

---

## 6. Test Commands

After merge, verify:
```bash
cd ~/Projects/hermes-agent
python -c "from tools.url_safety import is_safe_url; print(is_safe_url('https://example.com'))"  # Should print True
python -c "from tools.url_safety import is_safe_url; print(is_safe_url('http://localhost:8080'))"  # Should print False
python -c "from tools.web_tools import web_extract_tool, web_crawl_tool"  # Should import without error
```

---

## 7. Conflict Risk Assessment

- **Risk Level**: LOW
- **Reason**: The SSRF protection is additive - it adds checks before existing code
- **Page Storage**: Preserved - no changes to storage functions
- **Line Shift**: After patches, line numbers will shift by ~6-8 lines per insertion

### Page Storage Preservation

The local Page Storage feature is **fully preserved** in this merge:

| Function | Location | Purpose |
|----------|----------|---------|
| `store_page()` | Lines 178-240 | Store single page in SQLite |
| `store_pages_from_results()` | Lines 243-269 | Batch store from tool results |
| `search_pages()` | Lines 272-332 | FTS5 full-text search |
| `list_pages()` | Lines 335-415 | List with filtering |
| `get_page()` | Lines 418-469 | Retrieve by URL/ID |
| `delete_page()` | Lines 472-507 | Delete by URL/ID |
| `get_storage_stats()` | Lines 510-540 | Storage statistics |

**Storage calls in tools** (preserved after merge):
- `web_extract_tool` line ~1656: `store_pages_from_results(trimmed_results, source_tool="web_extract")`
- `web_crawl_tool` Tavily path line ~1800: `store_pages_from_results(trimmed_results, source_tool="web_crawl")`
- `web_crawl_tool` Firecrawl path line ~2063: `store_pages_from_results(trimmed_results, source_tool="web_crawl")`

The storage happens **after** all SSRF checks, so blocked URLs are stored with their error messages (as expected behavior).

---

## 8. Key Security Behavior

The `is_safe_url()` function blocks:
- `localhost`, `127.0.0.1`, `0.0.0.0`
- Private IP ranges (10.x.x.x, 172.16-31.x.x, 192.168.x.x)
- Link-local addresses (169.254.x.x) - includes AWS/GCP metadata
- Cloud metadata hostnames (metadata.google.internal)
- CGNAT range (100.64.0.0/10)
- DNS resolution failures (fails closed)

This prevents SSRF attacks where malicious prompts could trick the agent into:
- Accessing cloud metadata endpoints (AWS: 169.254.169.254)
- Scanning internal network services
- Accessing local development servers
