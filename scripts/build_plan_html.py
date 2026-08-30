"""Rebuild the plan HTML from the markdown, reusing the artifact's stylesheet.

Generated rather than hand-edited: the two had drifted apart across a day of edits,
and keeping a hand-maintained HTML copy of a 1200-line document in sync by hand is
how they diverge again.
"""
import re, sys
from pathlib import Path
import markdown

SP = Path("/private/tmp/claude-501/-Users-mac-Desktop-Work-and-Business-multimodal-form-filling/8741c6ff-6e30-4c7d-976d-8eddd6a6b588/scratchpad")
MD = Path("docs/app-implementation-plan.md")

head = (SP / "head.part").read_text(encoding="utf-8")
src = MD.read_text(encoding="utf-8")

# Pull mermaid fences out before conversion; markdown would escape them.
blocks = []
def stash(m):
    blocks.append(m.group(1))
    return f"\n@@MERMAID{len(blocks)-1}@@\n"
src = re.sub(r"```mermaid\n(.*?)```", stash, src, flags=re.S)

html = markdown.markdown(src, extensions=["tables", "fenced_code", "toc", "attr_list"])

THEME = ('%%{init:{"theme":"base","themeVariables":{"fontFamily":"JetBrains Mono, ui-monospace, monospace",'
         '"fontSize":"13px","primaryColor":"#ffffff","primaryTextColor":"#16191d",'
         '"primaryBorderColor":"#155e63","lineColor":"#5f6b78","tertiaryColor":"#f6f7f8"}}}%%')
for i, b in enumerate(blocks):
    plate = (f'<figure class="wide"><div class="plate"><pre class="mermaid">\n{THEME}\n{b}</pre></div></figure>')
    html = html.replace(f"<p>@@MERMAID{i}@@</p>", plate).replace(f"@@MERMAID{i}@@", plate)

# Use the ids the toc extension already assigned rather than minting our own —
# computing a second slug scheme is how five nav links ended up pointing at
# anchors that did not exist.
heads = re.findall(r'<h2 id="([^"]+)"[^>]*>(.*?)</h2>', html, flags=re.S)
missing = re.findall(r'<h2(?![^>]*\bid=)[^>]*>(.*?)</h2>', html, flags=re.S)
if missing:
    raise SystemExit(f"{len(missing)} h2 without an id: {missing[:2]}")

def label(t):
    return re.sub(r"<[^>]+>", "", t).strip()

nav = "\n".join(f'      <a href="#{i}">{label(t)}</a>' for i, t in heads)

body = f'''<div class="shell">
  <aside class="rail">
    <p class="rail-label">Contents</p>
    <nav id="toc">
{nav}
    </nav>
  </aside>
  <main>
    <header class="masthead">
      <p class="eyebrow">Implementation plan · v2</p>
      <h1>Form Validation Build Plan</h1>
      <p class="standfirst">An email-driven service that turns a free-text manifest and a pile of Word forms into reviewed documents &mdash; decomposed into branch-sized tasks that run in parallel.</p>
      <div class="meta">
        <span><b>Scope</b> email service + AI editor</span>
        <span><b>Source</b> email-form-validation-requirements.pdf</span>
        <span><b>Reqs</b> 17 + open concerns</span>
      </div>
    </header>
{html}
  </main>
</div>
<script>
(function(){{
  var links = Array.prototype.slice.call(document.querySelectorAll('#toc a'));
  var secs = links.map(function(a){{ return document.getElementById(a.getAttribute('href').slice(1)); }}).filter(Boolean);
  if(!secs.length) return;
  function sync(){{
    var y = window.scrollY + 120, cur = 0;
    for(var i=0;i<secs.length;i++){{ if(secs[i].offsetTop <= y) cur = i; }}
    links.forEach(function(a,i){{ a.classList.toggle('on', i===cur); }});
  }}
  var tick=false;
  window.addEventListener('scroll',function(){{ if(tick)return; tick=true;
    window.requestAnimationFrame(function(){{ sync(); tick=false; }}); }},{{passive:true}});
  sync();
}})();
</script>'''

EXTRA = """
<style>
  main h2{margin-top:3.2rem}
  main h2:first-of-type{margin-top:1rem}
  main table{margin:0 0 1.3rem}
  main > table, main > .tw{max-width:100%}
  main pre{background:var(--surface);border:1px solid var(--rule);border-radius:6px;
    padding:1.15rem 1.25rem;overflow-x:auto;font-family:var(--f-mono);font-size:.8125rem;
    line-height:1.62;margin:0 0 1.3rem}
  main pre.mermaid{background:none;border:none;padding:0;margin:0}
  main pre code{background:none;border:none;padding:0;font-size:1em}
  main blockquote{margin:0 0 1.3rem;padding:.6rem 0 .6rem 1.1rem;
    border-left:3px solid var(--accent);color:var(--muted);max-width:var(--col)}
  main blockquote p{margin:0}
  main table{border-collapse:collapse;width:100%;display:block;overflow-x:auto}
</style>
"""
(SP / "build-plan.html").write_text(head + EXTRA + "\n" + body + "\n", encoding="utf-8")
print(f"artifact source: {len(head+EXTRA+body)} chars, {len(blocks)} diagrams, {len(heads)} sections")
