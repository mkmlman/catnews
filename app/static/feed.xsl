<?xml version="1.0" encoding="utf-8"?>
<!--
  catnews feed stylesheet.
  Browsers apply this when a human opens feed.rss (or feed-<source>.rss);
  dedicated RSS readers skip it and parse the XML as usual. Self-contained
  by design: brand tokens inlined, no fonts or assets fetched.
-->
<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">
  <xsl:output method="html" doctype-system="about:legacy-compat" indent="yes"/>
  <xsl:template match="/rss">
    <html lang="en">
      <head>
        <meta charset="utf-8"/>
        <meta name="viewport" content="width=device-width, initial-scale=1"/>
        <title><xsl:value-of select="channel/title"/> — RSS</title>
        <style>
          :root { color-scheme: light dark; }
          * { margin: 0; padding: 0; box-sizing: border-box; }
          body {
            background: #faf9f6;
            color: #353431;
            font-family: Georgia, "Times New Roman", serif;
            font-size: 16px;
            line-height: 1.6;
            padding: 48px 20px 90px;
          }
          @media (prefers-color-scheme: dark) {
            body { background: #1a1a1a; color: #f0eee8; }
          }
          main { max-width: 680px; margin: 0 auto; }
          .eyebrow {
            font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
            font-size: 0.72rem;
            letter-spacing: 0.14em;
            text-transform: uppercase;
            opacity: 0.6;
            margin-bottom: 10px;
          }
          h1 {
            font-style: italic;
            font-weight: 400;
            font-size: 2rem;
            line-height: 1.15;
          }
          .sub { opacity: 0.72; margin-top: 6px; }
          .rule {
            width: 32px;
            height: 1px;
            background: currentColor;
            opacity: 0.4;
            margin: 20px 0 8px;
          }
          ol { list-style: none; }
          li {
            padding: 14px 0;
            border-top: 1px solid rgba(53, 52, 49, 0.18);
          }
          @media (prefers-color-scheme: dark) {
            li { border-color: rgba(240, 238, 232, 0.16); }
          }
          a {
            color: inherit;
            text-decoration: none;
            border-bottom: 1px dotted currentColor;
          }
          a:hover { border-bottom-style: solid; }
          .item-title { font-weight: 600; font-size: 1.06rem; line-height: 1.35; }
          .meta {
            display: block;
            margin-top: 3px;
            font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
            font-size: 0.72rem;
            letter-spacing: 0.05em;
            text-transform: uppercase;
            opacity: 0.55;
          }
          footer {
            margin-top: 34px;
            font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
            font-size: 0.72rem;
            letter-spacing: 0.06em;
            text-transform: uppercase;
            opacity: 0.62;
          }
        </style>
      </head>
      <body>
        <main>
          <header>
            <p class="eyebrow">RSS Feed</p>
            <h1><xsl:value-of select="channel/title"/></h1>
            <p class="sub"><xsl:value-of select="channel/description"/></p>
            <div class="rule"></div>
          </header>
          <ol>
            <xsl:for-each select="channel/item">
              <li>
                <a href="{link}"><span class="item-title"><xsl:value-of select="title"/></span></a>
                <span class="meta"><xsl:value-of select="author"/><xsl:if test="author"> · </xsl:if><xsl:value-of select="pubDate"/></span>
              </li>
            </xsl:for-each>
          </ol>
          <footer>This is an RSS feed — subscribe with any reader · <a href="{channel/link}">Visit the site →</a></footer>
        </main>
      </body>
    </html>
  </xsl:template>
</xsl:stylesheet>
