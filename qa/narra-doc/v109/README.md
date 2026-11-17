# 飞书文档“1116 精简版 01”和 HTML 演示（v109，11-16）
- cap24.mjs：按线上精简版（ui=v4）重截改过的 23 个界面（不花额度：写下一集等接口拦掉，/api/play 带 prewarm）。
  node cap24.mjs <playwright node_modules> "https://lyx1265897416-lab.github.io/unscripted-audio/?k=…&lang=en&ui=v4&debug=1" <out>/shots
- build24.py：从文档里当前 HTML 演示的数据（data_cur.json，可用 docx blocks API 读 html5 块的 add_ons.record 取回）出发，换掉改过的界面、重拼步骤图、出 viewer.html 和 table24.xml。
- 图片用 projects/cat-who-inherited/tools/mcp_upload.py 上传，链接在 urls24.tsv。
