---
layout: default
title: API Reference
parent: UI Documentation
nav_order: 4
---

# API Reference

This page documents the X2A Convertor REST API using the OpenAPI specification.

<div id="swagger-ui"></div>

<link rel="stylesheet" type="text/css" href="https://unpkg.com/swagger-ui-dist@5.31.0/swagger-ui.css" />
<script src="https://unpkg.com/swagger-ui-dist@5.31.0/swagger-ui-bundle.js"></script>
<script src="https://unpkg.com/swagger-ui-dist@5.31.0/swagger-ui-standalone-preset.js"></script>

<script>
window.onload = function() {
  const ui = SwaggerUIBundle({
    url: "https://raw.githubusercontent.com/redhat-developer/rhdh-plugins/refs/heads/main/workspaces/x2a/plugins/x2a-backend/src/schema/openapi.yaml",
    dom_id: '#swagger-ui',
    deepLinking: true,
    presets: [
      SwaggerUIBundle.presets.apis,
      SwaggerUIStandalonePreset
    ],
    plugins: [
      SwaggerUIBundle.plugins.DownloadUrl
    ],
    layout: "BaseLayout"
  })
  window.ui = ui
}
</script>

<style>
  .swagger-ui .topbar {
    display: none;
  }
</style>
