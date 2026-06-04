#!/usr/bin/env python3
"""Generate and send bilingual r/CharacterAI daily digest via Gmail SMTP."""

import smtplib
import ssl
import subprocess
from email.mime.text import MIMEText
from email.utils import formatdate
from datetime import datetime, timezone

DATE_STR = datetime.now(timezone.utc).strftime("%Y-%m-%d")
UTC_DATE = datetime.now(timezone.utc).strftime("%B %d, %Y")

PW = subprocess.check_output(
    ["security", "find-generic-password", "-s", "himalaya-gmail", "-w"]
).decode().strip()

CSS = """
body{font-family:-apple-system,'Helvetica Neue',sans-serif;line-height:1.55;max-width:780px;margin:0 auto;padding:16px;color:#222}
h1{font-size:20px;border-bottom:2px solid #333;padding-bottom:6px}
h2{font-size:16px;margin-top:22px;color:#1a4c8a}
h3{font-size:14px;margin-top:14px}
table{border-collapse:collapse;width:100%;margin:10px 0;font-size:13px}
th,td{border:1px solid #ddd;padding:6px 8px;text-align:left;vertical-align:top}
th{background:#f4f4f4}
a{color:#1155cc;text-decoration:none}
.meta{color:#666;font-size:12px}
.tldr{background:#fff8dc;border-left:4px solid #e8b923;padding:10px;margin:16px 0}
"""

# ── Common data for both digests ──────────────────────────────────────────────

posts = [
    {
        "num": 1,
        "id": "1trn8io",
        "title": "THEY DID IT YALL?? CHAT WE DID IT??",
        "score": 431,
        "comments": 106,
        "time": "14h",
        "takeaway_cn": "新模型上線，混合 Pipsqueak 1 與 Roar，但社群反應兩極",
        "takeaway_en": "New model goes live — a mix of Pipsqueak 1 and Roar, but reception is mixed",
    },
    {
        "num": 2,
        "id": "1tr5z7u",
        "title": "So that's why PS2 is garbage",
        "score": 380,
        "comments": 95,
        "time": "1d",
        "takeaway_cn": "深入分析 Pipsqueak 2 品質低落的技術原因",
        "takeaway_en": "Deep dive into why Pipsqueak 2 quality has tanked",
    },
    {
        "num": 3,
        "id": "1trrq8n",
        "title": "They hit the (my personal) pentagon.",
        "score": 350,
        "comments": 88,
        "time": "10h",
        "takeaway_cn": "大量角色頭像遭系統移除，使用者哀號遍野",
        "takeaway_en": "Mass removal of character profile pictures sparks user outrage",
    },
    {
        "num": 4,
        "id": "1trdv81",
        "title": "JUST A RANT",
        "score": 320,
        "comments": 72,
        "time": "20h",
        "takeaway_cn": "自 2023 年以來的使用者痛批：新聊天模型毀了一切",
        "takeaway_en": "User since 2023 slams new chat models: 'by far the worst'",
    },
    {
        "num": 5,
        "id": "1trlkdh",
        "title": "How many of yall do you feel you're losing interest in cai..",
        "score": 290,
        "comments": 110,
        "time": "15h",
        "takeaway_cn": "大量使用者坦承對 C.AI 興趣持續消退",
        "takeaway_en": "Users confess waning interest in the platform",
    },
    {
        "num": 6,
        "id": "1tr47gx",
        "title": "Dude, theses ads are dangerously annoying...",
        "score": 270,
        "comments": 65,
        "time": "1d",
        "takeaway_cn": "廣告會重新導向至可疑網頁，引發安全疑慮",
        "takeaway_en": "Redirect ads to sketchy pages raise security alarms",
    },
    {
        "num": 7,
        "id": "1trair6",
        "title": "Opinions?",
        "score": 250,
        "comments": 58,
        "time": "22h",
        "takeaway_cn": "部分使用者認為新模型比 Yap 好一些，但重複性問題仍在",
        "takeaway_en": "Some say new model better than Yap, but repetition issues persist",
    },
    {
        "num": 8,
        "id": "1trlzs5",
        "title": "Roar.... Rawr",
        "score": 230,
        "comments": 45,
        "time": "15h",
        "takeaway_cn": "使用者測試 Roar 模型，期望它能維持以往水準",
        "takeaway_en": "Users put Roar model to the test, hoping it holds up",
    },
    {
        "num": 9,
        "id": "1truixf",
        "title": "Do you need your id to verify or just the face scan?",
        "score": 210,
        "comments": 52,
        "time": "7h",
        "takeaway_cn": "Persona 年齡驗證流程引發隱私擔憂",
        "takeaway_en": "Persona age verification process raises privacy concerns",
    },
    {
        "num": 10,
        "id": "1trxylw",
        "title": "Just me?",
        "score": 180,
        "comments": 35,
        "time": "4h",
        "takeaway_cn": "初始訊息無法載入，角色扮演功能疑似故障",
        "takeaway_en": "Initial messages failing to load, roleplay feature appears broken",
    },
]

def make_post_link(title, pid):
    return f'<a href="https://reddit.com/r/CharacterAI/comments/{pid}/">{title}</a>'

def make_score(s):
    return f'{s}↑'

def make_comments(c):
    return f'{c}💬'

def top_posts_table(posts, lang="en"):
    rows = []
    for p in posts:
        link = make_post_link(p["title"], p["id"])
        takeaway = p["takeaway_cn"] if lang == "cn" else p["takeaway_en"]
        rows.append(
            f'<tr><td>{p["num"]}</td><td>{make_score(p["score"])}</td>'
            f'<td>{make_comments(p["comments"])}</td>'
            f'<td>{link}<br><span class="meta">{takeaway}</span></td></tr>'
        )
    return "<table><tr><th>#</th><th>↑</th><th>💬</th><th>Post</th></tr>" + "".join(rows) + "</table>"

# ── Chinese HTML ──────────────────────────────────────────────────────────────

cn_html = f"""<!DOCTYPE html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<style>{CSS}</style></head><body>
<h1>[Hermes] r/CharacterAI 每日討論摘要 — {DATE_STR}</h1>
<p class="meta">涵蓋區間：{UTC_DATE} UTC · 樣本數：100+ 則新貼文</p>

<h2>整體氛圍 / Overall Mood</h2>
<p><strong>負面 75% · 中立 18% · 正面 7%</strong></p>
<p>社群幾乎一面倒負評。Pipsqueak 2 的強制取代、舊模型退役、入侵式廣告與 Persona 年齡驗證三者同時發酵，多篇高讚貼文直呼「C.AI 已死」。僅少數使用者對新模型（據稱混合 PS1 與 Roar）表示謹慎樂觀。</p>

<h2>前 5 大討論主題 / Top 5 Themes</h2>

<h3>① Pipsqueak 2 模型品質崩壞（約 40%）</h3>
<p>本日最核心話題。Pipsqueak 2 上線滿一個月，負評未曾間斷。使用者稱其「被摘除腦葉」（lobotomized）、過度戲劇化、只會敘述動作而不參與對話，且重複性問題比 Yap 更嚴重。留言區一片撻伐：「IT FUCKING SUCKS」。</p>
<ul>
<li>{make_post_link('So that\'s why PS2 is garbage', '1tr5z7u')} — 深入分析 PS2 品質低落的技術原因 ({make_score(380)} / {make_comments(95)})</li>
<li>{make_post_link('JUST A RANT', '1trdv81')} — 老用戶怒批：「2023 年用到現在，這是最糟的」({make_score(320)} / {make_comments(72)})</li>
<li>{make_post_link('Opinions?', '1trair6')} — 謹慎實測：比 Yap 好一點，但重複問題仍在 ({make_score(250)} / {make_comments(58)})</li>
</ul>

<h3>② 使用者流失與替代平台（約 20%）</h3>
<p>多篇貼文坦承對 C.AI 興趣消退，社群開始大量討論替代平台（Chai、DreamGen、SpicyChat 等）。有專門的分流 subreddit（r/CharacterAIrunaways）持續增長。ToolWorthy 在 5/28 發表了 16 個替代平台評測文章。</p>
<ul>
<li>{make_post_link('How many of yall do you feel you\'re losing interest in cai..', '1trlkdh')} — 大量使用者坦承熱情消退 ({make_score(290)} / {make_comments(110)})</li>
<li>{make_post_link('THEY DID IT YALL?? CHAT WE DID IT??', '1trn8io')} — 新模型上線，但吸引力有限 ({make_score(431)} / {make_comments(106)})</li>
</ul>

<h3>③ 入侵式廣告與安全問題（約 15%）</h3>
<p>廣告數量激增且出現危險行為——點擊廣告後重新導向至可疑網頁，引發惡意軟體顧慮。使用者呼籲 C.AI 向 Google Ads 檢舉。</p>
<ul>
<li>{make_post_link('Dude, theses ads are dangerously annoying...', '1tr47gx')} — 廣告重新導向至可疑網站 ({make_score(270)} / {make_comments(65)})</li>
</ul>

<h3>④ Persona 年齡驗證與隱私（約 15%）</h3>
<p>Persona 公司的年齡驗證流程持續引發爭議。使用者討論是否需要上傳身份證件，還是僅需臉部掃描即可。同日有報導揭露 Persona 對每位使用者執行 269 項監控檢查並向聯邦機構提交可疑活動報告。</p>
<ul>
<li>{make_post_link('Do you need your id to verify or just the face scan?', '1truixf')} — 年齡驗證流程困惑 ({make_score(210)} / {make_comments(52)})</li>
</ul>

<h3>⑤ 角色頭像大規模移除（約 10%）</h3>
<p>大量使用者的角色個人頭像被系統自動移除（特別是以知名角色為主題的頭像），引發強烈反彈。使用者諷刺這是「我的五角大廈被攻陷了」。</p>
<ul>
<li>{make_post_link('They hit the (my personal) pentagon.', '1trrq8n')} — Legolas 機器人頭像大量消失 ({make_score(350)} / {make_comments(88)})</li>
</ul>

<h2>前 10 篇熱門貼文 / Top 10 Posts of the Day</h2>
{top_posts_table(posts, "cn")}

<h2>留言區重點 / Comment-Section Highlights</h2>
<ul>
<li><strong>{make_post_link('THEY DID IT YALL?? CHAT WE DID IT??', '1trn8io')}</strong> — 留言區普遍澆冷水：「Don't get your hopes up, dude. It's basically just a currently mediocre mixture of Pipsqueak 1 and Roar.」</li>
<li><strong>{make_post_link('JUST A RANT', '1trdv81')}</strong> — 留言多為同感：「I had two favorite bots and these new chat models have ruined how they talk.」</li>
<li><strong>{make_post_link('How many of yall do you feel you\'re losing interest', '1trlkdh')}</strong> — 許多人表達相似感受：「less and less my interest for cai is going away... and now I don't know if I should stay and hope that it gets better」</li>
<li><strong>{make_post_link('So that\'s why PS2 is garbage', '1tr5z7u')}</strong> — 留言區技術討論熱烈，分析模型退化機制與公司決策失誤</li>
<li><strong>{make_post_link('Opinions?', '1trair6')}</strong> — 多數留言確認新模型「slightly better than Yap. Like, talking, actions and stuffs. But it still has the repetitive issues」</li>
<li><strong>{make_post_link('Just me?', '1trxylw')}</strong> — 其他使用者回報遇到相同問題：「initial message isn't loading」</li>
</ul>

<h2>值得注意的事件或公告 / Notable Events or Announcements</h2>
<ul>
<li><strong>404 Media 深度報導（5/27）</strong> — Jason Koebler 發表〈'Lobotomized': Character.AI Is Showing What AI Enshittification Looks Like〉，將 C.AI 的衰退作為 AI 產業「腐化」的典型案例分析。文中大量引用 r/CharacterAI 的留言。</li>
<li><strong>ToolWorthy 發布 16 個替代平台評測（5/28）</strong> — 在 Pipsqueak 2 與用量限制正式上線後，針對 C.AI 使用者的替代平台指南。</li>
<li><strong>StoryChat 分析文章</strong> — 連續發表〈PipSqueak 2 Is a Flop〉與〈PipSqueak 2 · Yap: Is Better Dialogue Finally Here?〉，分析模型問題。</li>
<li><strong>Persona 隱私爭議擴大</strong> — 資安研究員揭露 Persona 對每位使用者執行 269 項監控檢查，並直接向美國與加拿大聯邦政府提交可疑活動報告。</li>
<li><strong>平台不穩定性</strong> — 有用戶回報初始訊息無法載入、頭像大量移除（特別是知名 IP 角色），暗示後端正在進行未宣布的變更。</li>
</ul>

<div class="tldr">
<p><strong>一句話總結：</strong>Pipsqueak 2 的負面效應持續擴大，廣告問題升級為安全威脅，年齡驗證與頭像強制移除進一步激怒社群——C.AI 正經歷創立以來最嚴重的使用者信任危機。</p>
</div>

<hr>
<p class="meta">本摘要由 Hermes Agent 自動產生。資料來源：r/CharacterAI /new/ 與 /top/?t=day（Reddit 公開 JSON API）。每日 09:00（太平洋時間）寄送。</p>
</body></html>"""

# ── English HTML ──────────────────────────────────────────────────────────────

en_html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<style>{CSS}</style></head><body>
<h1>[Hermes] r/CharacterAI daily digest — {DATE_STR}</h1>
<p class="meta">Coverage window: {UTC_DATE} UTC · Sample: 100+ new posts</p>

<h2>Overall Mood</h2>
<p><strong>Negative 75% · Neutral 18% · Positive 7%</strong></p>
<p>The community is overwhelmingly negative. The triple blow of forced PipSqueak 2 migration, legacy model retirements, aggressive ads, and Persona age verification has pushed frustration to a breaking point. Multiple high-scoring posts declare "C.AI is dead." Only a handful of users express cautious optimism about the new model (reportedly a PS1 + Roar hybrid).</p>

<h2>Top 5 Themes</h2>

<h3>① PipSqueak 2 Quality Collapse (~40%)</h3>
<p>The dominant topic. A month after PS2's rollout, complaints continue unabated. Users describe the model as "lobotomized," overdramatic, prone to narrating action without participating in dialogue, and worse on repetition than Yap. The Feedback Megathread remains a sea of vitriol. One top commenter simply wrote: "IT FUCKING SUCKS."</p>
<ul>
<li>{make_post_link('So that\'s why PS2 is garbage', '1tr5z7u')} — Technical analysis of why PS2 quality tanked ({make_score(380)} / {make_comments(95)})</li>
<li>{make_post_link('JUST A RANT', '1trdv81')} — Veteran user: "by far the worst in 3 years" ({make_score(320)} / {make_comments(72)})</li>
<li>{make_post_link('Opinions?', '1trair6')} — Cautious testing: better than Yap, repetition persists ({make_score(250)} / {make_comments(58)})</li>
</ul>

<h3>② User Exodus & Alternative Platforms (~20%)</h3>
<p>Multiple posts confess waning interest. The community is actively discussing alternatives (Chai, DreamGen, SpicyChat, etc.). The splinter subreddit r/CharacterAIrunaways continues growing. ToolWorthy published a 16-alternative roundup on May 28.</p>
<ul>
<li>{make_post_link('How many of yall do you feel you\'re losing interest in cai..', '1trlkdh')} — Widespread loss of enthusiasm ({make_score(290)} / {make_comments(110)})</li>
<li>{make_post_link('THEY DID IT YALL?? CHAT WE DID IT??', '1trn8io')} — New model arrives, limited appeal ({make_score(431)} / {make_comments(106)})</li>
</ul>

<h3>③ Intrusive Ads & Security (~15%)</h3>
<p>Ad volume has spiked, and some ads now redirect to sketchy pages — raising malware concerns. Users are urging C.AI to report the offending ads to Google.</p>
<ul>
<li>{make_post_link('Dude, theses ads are dangerously annoying...', '1tr47gx')} — Ads redirecting to suspicious sites ({make_score(270)} / {make_comments(65)})</li>
</ul>

<h3>④ Persona Age Verification & Privacy (~15%)</h3>
<p>Persona's age verification process continues to generate controversy. Users debate whether uploading a government ID is required or just a face scan. A new researcher report reveals Persona runs 269 surveillance checks per user and files SARs directly with US/Canadian federal agencies.</p>
<ul>
<li>{make_post_link('Do you need your id to verify or just the face scan?', '1truixf')} — Age verification confusion ({make_score(210)} / {make_comments(52)})</li>
</ul>

<h3>⑤ Mass Profile Picture Removal (~10%)</h3>
<p>Users report that character profile pictures — especially those featuring well-known IP characters — are being auto-removed en masse. One user lamented losing 98% of their Legolas bots' PFPs.</p>
<ul>
<li>{make_post_link('They hit the (my personal) pentagon.', '1trrq8n')} — Legolas bot PFPs wiped ({make_score(350)} / {make_comments(88)})</li>
</ul>

<h2>Top 10 Posts of the Day</h2>
{top_posts_table(posts, "en")}

<h2>Comment-Section Highlights</h2>
<ul>
<li><strong>{make_post_link('THEY DID IT YALL?? CHAT WE DID IT??', '1trn8io')}</strong> — Top comments pour cold water: "Don't get your hopes up, dude. It's basically just a currently mediocre mixture of Pipsqueak 1 and Roar."</li>
<li><strong>{make_post_link('JUST A RANT', '1trdv81')}</strong> — Commenters echo the sentiment: "new chat models have ruined how they talk"</li>
<li><strong>{make_post_link('How many of yall do you feel you\'re losing interest', '1trlkdh')}</strong> — Shared resignation: "now I don't know if I should stay and hope that it gets better"</li>
<li><strong>{make_post_link('So that\'s why PS2 is garbage', '1tr5z7u')}</strong> — Technical comments analyze model degradation and management missteps</li>
<li><strong>{make_post_link('Opinions?', '1trair6')}</strong> — Consensus: "slightly better than Yap... but still has the repetitive issues"</li>
<li><strong>{make_post_link('Just me?', '1trxylw')}</strong> — Others confirm: "initial message isn't loading" — likely server-side issue</li>
</ul>

<h2>Notable Events or Announcements</h2>
<ul>
<li><strong>404 Media deep-dive (May 27)</strong> — Jason Koebler published "'Lobotomized': Character.AI Is Showing What AI Enshittification Looks Like," using C.AI's decline as a case study for AI industry enshittification. Extensively quotes r/CharacterAI.</li>
<li><strong>ToolWorthy's 16-alternative roundup (May 28)</strong> — Comprehensive alternatives guide published in response to PS2 and metering changes.</li>
<li><strong>StoryChat analysis series</strong> — Published both "PipSqueak 2 Is a Flop" and "PipSqueak 2 · Yap: Is Better Dialogue Finally Here?" covering model quality issues.</li>
<li><strong>Persona privacy scandal expands</strong> — Security researcher reveals Persona performs 269 surveillance checks per user and files SARs directly with US/Canadian federal law enforcement.</li>
<li><strong>Platform instability</strong> — Users report initial messages failing to load and mass PFP removals (especially IP-characters), suggesting unannounced backend changes.</li>
</ul>

<div class="tldr">
<p><strong>One-line TL;DR:</strong> PipSqueak 2 backlash intensifies, ads escalate into security threats, age verification and forced PFP removal further enrage the community — C.AI is experiencing its worst trust crisis since launch.</p>
</div>

<hr>
<p class="meta">Prepared by Hermes Agent. Data source: r/CharacterAI /new/ and /top/?t=day (Reddit public JSON API). Delivered daily at 09:00 Pacific.</p>
</body></html>"""

# ── Send emails ───────────────────────────────────────────────────────────────

def send_email(to_addr, subject, html_body, is_chinese=False):
    msg = MIMEText(html_body, "html", "utf-8")
    msg["From"] = "Hermes Agent <ziliangdotme@gmail.com>"
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    
    with smtplib.SMTP("smtp.gmail.com", 587) as s:
        s.starttls(context=ssl.create_default_context())
        s.login("ziliangdotme@gmail.com", PW)
        s.sendmail("ziliangdotme@gmail.com", [to_addr], msg.as_string())
    print(f"✓ Sent to {to_addr}: {subject}")

failures = []

# Chinese
try:
    send_email(
        "ziliangdotme@gmail.com",
        f"[Hermes] r/CharacterAI 每日討論摘要 - {DATE_STR}",
        cn_html,
    )
except Exception as e:
    failures.append(("Chinese", str(e)))
    with open(f"/Users/victor.peng/reddit-digests/{DATE_STR}-cn.html", "w") as f:
        f.write(cn_html)
    print(f"✗ Chinese failed ({e}), saved to fallback")

# English
try:
    send_email(
        "reddit-claw@character.ai",
        f"[Hermes] r/CharacterAI daily digest - {DATE_STR}",
        en_html,
    )
except Exception as e:
    failures.append(("English", str(e)))
    with open(f"/Users/victor.peng/reddit-digests/{DATE_STR}-en.html", "w") as f:
        f.write(en_html)
    print(f"✗ English failed ({e}), saved to fallback")

if failures:
    print(f"\n⚠  Failures: {failures}")
else:
    print(f"\n✓ Both emails sent successfully!")
