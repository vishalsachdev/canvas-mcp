# Plan: Improve Canvas MCP Search Discoverability

## Problem
When searching "canvas mcp", the site doesn't rank well on search engines despite having good content.

## Current State
- ✅ Custom domain configured (canvas-mcp.illinihunt.org)
- ✅ MCP registry (server.json) well-tagged
- ✅ Basic meta tags present
- ❌ No sitemap.xml
- ❌ No robots.txt
- ❌ No structured data (JSON-LD)
- ❌ No Twitter card meta tags
- ❌ No og:image for social previews
- ❌ No canonical URLs

## Implementation Plan

### 1. Add SEO Meta Tags to docs/index.html
Add to `<head>`:
- Twitter card tags (`twitter:card`, `twitter:site`, `twitter:title`, `twitter:description`, `twitter:image`)
- Canonical URL (`<link rel="canonical">`)
- `og:image` meta tag (use a preview image)
- Additional structured keywords

### 2. Create docs/sitemap.xml
```xml
<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://canvas-mcp.illinihunt.org/</loc></url>
  <url><loc>https://canvas-mcp.illinihunt.org/student-guide.html</loc></url>
  <url><loc>https://canvas-mcp.illinihunt.org/educator-guide.html</loc></url>
  <url><loc>https://canvas-mcp.illinihunt.org/bulk-grading.html</loc></url>
</urlset>
```

### 3. Create docs/robots.txt
```
User-agent: *
Allow: /
Sitemap: https://canvas-mcp.illinihunt.org/sitemap.xml
```

### 4. Add JSON-LD Structured Data to docs/index.html
Add `SoftwareApplication` schema:
```json
{
  "@context": "https://schema.org",
  "@type": "SoftwareApplication",
  "name": "Canvas MCP",
  "description": "AI-powered Canvas LMS integration with 80+ tools",
  "applicationCategory": "EducationalApplication",
  "operatingSystem": "Cross-platform",
  "offers": { "@type": "Offer", "price": "0" },
  "author": { "@type": "Person", "name": "Vishal Sachdev" }
}
```

## Files to Modify/Create
| File | Action |
|------|--------|
| `docs/index.html` | Add Twitter cards, canonical, JSON-LD structured data |
| `docs/sitemap.xml` | Create new |
| `docs/robots.txt` | Create new |

*(Social preview image skipped for now - can add later)*

## Verification
1. Run Google's Rich Results Test on the URL
2. Use Twitter Card Validator to test social previews
3. Use Facebook Sharing Debugger for OG tags
4. Submit sitemap to Google Search Console
5. Check indexing status after 1-2 weeks

## Notes
- Changes take time to reflect in search rankings (weeks to months)
- Consider submitting to Google Search Console manually to speed up indexing
- MCP-specific directories (modelcontextprotocol.io) already index via server.json
