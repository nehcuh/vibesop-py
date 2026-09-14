"""Build a self-contained reading preview; embeds only article PNGs, no raw experiment data."""
from pathlib import Path
import base64, re, json, hashlib
import markdown
from bs4 import BeautifulSoup
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
SOURCE=ROOT/'docs/2026-09-12-agent-trust-wechat.md'
OUT=SOURCE.with_suffix('.html')
body=markdown.markdown(SOURCE.read_text(),extensions=['extra','toc'],output_format='html')
soup=BeautifulSoup(body,'html.parser')
for im in soup.find_all('img'):
 p=Path(im['src']);im['src']='data:image/png;base64,'+base64.b64encode(p.read_bytes()).decode();im['loading']='eager';im['decoding']='sync'
for tab in soup.find_all('table'):
 headers=[x.get_text() for x in tab.select('thead th')]
 for row in tab.select('tbody tr'):
  for i,td in enumerate(row.find_all('td',recursive=False)):
   if i<len(headers):td['data-label']=headers[i]
for p in soup.find_all('p'):
 if p.get_text().startswith('图') and p.find('em'):p['class']='caption'
for a in soup.find_all('a'):
 href=a.get('href','')
 if href.startswith('/Users/'):
  a.name='span'
  a.attrs={'class':'local-reference','title':'仓库证据索引；完整本地链接保留在 Markdown 源稿'}
css='''
*{box-sizing:border-box}html{background:#f1f0ea;color:#243640}body{margin:0;font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Hiragino Sans GB",sans-serif}article{max-width:740px;margin:32px auto;background:#fffdf8;padding:54px 48px 60px;border-radius:8px}.kicker{font-size:12px;letter-spacing:2px;color:#16756f;font-weight:700;margin-bottom:24px}h1{font-size:33px;line-height:1.45;letter-spacing:-.7px;margin:0 0 30px;font-weight:750}h2{font-size:25px;line-height:1.55;border-top:1px solid #d7dfdc;padding-top:28px;margin:52px 0 24px}h3{font-size:21px;line-height:1.65;margin:36px 0 18px}p,li{font-size:17px;line-height:1.95;letter-spacing:.2px;margin:0 0 20px}strong{font-weight:700;color:#153f3c}a{color:#16756f;text-decoration:none;border-bottom:1px solid #a6c8c1;overflow-wrap:anywhere}img{display:block;width:100%;height:auto;border-radius:5px;margin:26px 0 0}.caption,.caption em{font-style:normal;font-size:12.5px;line-height:1.8;color:#66767a}.caption{margin-top:-8px;padding:0 4px 4px}blockquote{margin:28px 0;padding:18px 24px;background:#e5f0ef;border-left:4px solid #16756f}blockquote p{margin:0}code{overflow-wrap:anywhere;word-break:break-word;font-size:.89em;padding:2px 5px;background:#edf1eb;border-radius:4px}table{width:100%;border-collapse:collapse;margin:26px 0 30px;font-size:14px;line-height:1.85}th{text-align:left;background:#e5f0ef}th,td{padding:11px 10px;vertical-align:top;border-bottom:1px solid #d7dfdc}td:first-child{font-weight:600}li{margin-bottom:12px}ul{padding-left:24px}hr{border:0;border-top:1px solid #d7dfdc;margin:42px 0}article>p:last-child{font-size:13px;color:#67777c}.endmark{font-size:11px;letter-spacing:2px;color:#8b9595;margin-top:44px} @media(max-width:520px){article{margin:0;border-radius:0;padding:30px 23px 40px}h1{font-size:29px}h2{font-size:23px;margin-top:40px}p,li{font-size:17px;line-height:1.95}blockquote{padding:15px 18px}thead{display:none}table,tbody,tr,td{display:block;width:100%}tr{background:#f4f5ef;margin-bottom:14px;border-radius:5px;padding:5px 8px}td{font-size:14px;display:grid;grid-template-columns:26% 1fr;gap:10px;padding:9px 5px}td:before{content:attr(data-label);font-size:12px;font-weight:600;color:#67777c}td:last-child{border:0}.caption,.caption em{font-size:12px}} @media print{html{background:white}article{margin:0;max-width:none}h2{break-after:avoid}img,tr{break-inside:avoid}}
'''
OUT.write_text('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>给 AI 配了七个专家，为什么未必比一个模型强？</title><style>'+css+'</style></head><body><article><div class="kicker">VIBESOP / 实验手记 · 2026.09.14 更新</div>'+str(soup)+'<div class="endmark">基于实际项目记录 · 原始评分与局限保留</div></article></body></html>')
links=[]
for dest in re.findall(r'!?\[[^\]]*\]\(([^)]+)\)',SOURCE.read_text()):
 if dest.startswith('/'):links.append({'path':dest,'exists':Path(dest).exists()})
missing=[x['path'] for x in links if not x['exists']]
print(json.dumps({'html':str(OUT),'article_chars':len(SOURCE.read_text()),'images':len(soup.find_all('img')),'local_links':len(links),'missing':missing},ensure_ascii=False))
if missing:raise SystemExit(1)
