# 11-16 v109 精简版进文档：从当前 HTML 演示的数据出发，换掉改过的界面，重拼步骤图，出 viewer.html 和静态表格
import json, os, sys, html, urllib.request
from PIL import Image, ImageDraw, ImageFont
cur = json.load(open('data_cur.json')); OLD = {s['id']: s for st in cur for s in st['screens']}
NAV = ([0, 785, 390, 59], '底部导航', 'Home、Rewards、Me 三个标签；书架并进了 Me')
def M(*ms): return [{'r': list(m[0]) if isinstance(m[0], (list, tuple)) else list(m[:4]), 'n': m[-2], 'd': m[-1], 'pt': False} for m in ms]
def mk(x, y, w, h, n, d): return {'r': [x, y, w, h], 'n': n, 'd': d, 'pt': False}
NEW = {
 '01-onboard-welcome': ('欢迎页', [mk(22,12,346,14,'步骤进度','一共两步：欢迎、一段小戏'), mk(0,74,390,400,'封面拼图','片库里几位主角的封面'), mk(22,474,346,67,'产品主张','Stories that listen back：接下来发生什么，你说了算'), mk(22,558,346,66,'三步图示','听、回应、为你现写，用图标代替大段说明；三个图标顶端对齐'), mk(22,780,346,54,'Get started','进入小戏')]),
 '02-ob-name': ('角色问你叫什么', [mk(327,6,49,44,'Skip','随时跳过引导，回首页'), mk(22,26,346,65,'角色','Rian，《人鱼王子的假新娘》的男主'), mk(22,105,346,61,'旁白','开场一句，播放剧里的真实配音'), mk(22,176,346,64,'提问','Rian 问你该怎么叫你：引导里“你是谁”就从这里来'), mk(22,734,288,50,'名字输入框','填了角色会在故事里叫你的名字，也是账户名'), mk(157,790,76,44,'Not now','不填也能继续')]),
 '03-ob-turn': ('第一个选择', [mk(22,249,346,42,'你的名字','你发出的话是渐变气泡'), mk(22,301,346,116,'角色回应','先叫你的名字，再说一句真实配音的台词'), mk(22,426,346,244,'轮到你','和正式收听里的选择点一样：一句情境，两个选项'), mk(36,523,318,104,'A / B','点一个就行'), mk(22,784,346,50,'说或打','左边麦克风直接说（本地识别），也可以打自己的回答')]),
 '04-ob-end': ('接一句后开播', [mk(22,481,346,42,'你的回答','你刚选的'), mk(22,533,346,64,'角色接话','按你的回答接一句：演示“下一段按你的话写”'), mk(22,610,346,110,'第 1 集','就是这部剧，每一集都停在轮到你的时候'), mk(22,730,346,44,'Start listening','直接开播第 1 集，不经过首页和选题材'), mk(125,782,139,44,'Browse all stories','先去首页看看别的剧')]),
 '04-home': ('首页（顶部）', [mk(255,10,44,44,'搜索','点开才出现搜索栏'), mk(301,15,73,34,'金币','当前余额，点开是金币商店'), mk(16,68,358,412,'主推大图','左右滑动换剧'), mk(32,359,326,55,'剧名和主角','大图上只留剧名和主角，三行简介去掉了'), mk(32,424,117,40,'Play Now','不进详情，直接播第 1 集'), mk(16,514,358,36,'题材筛选','点一个题材，直接进搜索状态并筛好这一类'), mk(16,572,358,170,'Top 10 this week','按播放量排名'), mk(*NAV[0], NAV[1], NAV[2])]),
 '05-home-shelves': ('首页（下滑）', OLD['05-home-shelves']['marks']),
 '06-home-more': ('首页（分类）', OLD['06-home-more']['marks']),
 '53-home-end': ('首页（底部）', [mk(16,54,358,640,'All series','全部剧集的列表'), mk(16,700,358,56,'免费时长和福利','还剩多少分钟免费收听；点 Claim 去福利页（副标题和底部说明去掉了）')]),
 '26-mini-player': ('继续收听', [mk(16,253,358,30,'Continue Listening','老用户在主推大图下面就能看到；See all 去“我的”里的在听'), mk(16,292,96,96,'封面','点开接着听'), mk(124,296,210,50,'上次收听','多久之前听的、剧名、第几集'), mk(124,353,114,34,'播放胶囊','播放键、进度；轮到你选时显示 Your move'), mk(298,352,36,36,'更多','剧集详情、移出在听')]),
 '42-unlock-sheet': ('解锁弹层', [mk(153,336,84,84,'带锁的封面','要解锁的这部剧'), mk(18,428,354,50,'Unlock Episode 4','前 30 分钟免费用完之后，第 4 集起每集要解锁（截图为手动调出）'), mk(18,494,354,45,'Price','每集 10 金币'), mk(18,551,354,45,'Your balance','当前金币余额'), mk(18,608,354,52,'Unlock with 10 coins','扣 10 金币，开始写这一集'), mk(18,670,354,48,'Wait-free','倒计时走完可免费解锁；不做广告，看广告解锁去掉了'), mk(18,728,354,44,'Get more coins','打开金币商店'), mk(18,776,354,54,'Auto-unlock','打开后每次做完选择自动扣金币解锁'), mk(338,300,44,44,'关闭','不解锁，回到播放页')]),
 '43-unlock-no-coins': ('金币不够时', [mk(18,605,354,45,'Your balance','余额不够 10 金币'), mk(18,662,354,52,'Not enough coins · Get more','主按钮变成去金币商店充值'), mk(18,724,354,48,'Wait-free','或者等倒计时走完')]),
 '24-listening-mode': ('收听模式', [mk(18,596,354,70,'Hands-free','旁白念出问题，你直接说'), mk(18,676,354,70,'Lean back','不提问，故事自己往下走'), mk(18,756,354,70,'Tap to choose','在屏幕上点选；每种只留一句话')]),
 '60-me': ('我的（在听）', [mk(16,18,56,56,'头像','点一下从相册换头像'), mk(84,22,75,28,'名字','账户名；登录后旁边有笔，点了改名'), mk(84,50,254,22,'概况','听过几部剧、当前收听方式'), mk(340,10,44,44,'设置','经典齿轮，和首页右上角按钮同一高度'), mk(16,92,358,181,'我的钱包','金币、剩余免费分钟和进度条'), mk(270,163,88,36,'Get coins','打开金币商店'), mk(32,235,326,25,'收费规则','两行说明缩成两个小标签：每部前 3 集免费、之后每集 10'), mk(16,293,200,40,'两个分类','Listening 在听、Saved 收藏'), mk(16,347,358,220,'封面网格','一行三部；点封面接着听'), mk(16,587,111,186,'轮到你了','停在选择点的剧，封面左下角有 Your move'), mk(340,291,34,44,'Edit','点了才出现移除按钮'), mk(*NAV[0], NAV[1], NAV[2])]),
 '61-me-edit': ('我的 · 编辑', [mk(105,339,30,30,'移除','编辑状态下每个封面右上角出现；这时封面本身点不动，避免误触'), mk(338,291,36,44,'Done','退出编辑')]),
 '62-me-saved': ('我的 · 收藏', [mk(136,293,72,40,'Saved','收藏的剧，和剧集页右上角的星标是同一件事'), mk(16,347,358,211,'收藏的剧','封面、剧名、主角；点开进详情')]),
 '63-settings': ('设置', [mk(18,252,80,24,'Settings','从“我的”右上角齿轮进来，只放设置'), mk(338,244,44,44,'关闭','回到“我的”'), mk(18,327,354,52,'收听方式','当前模式，点开切换'), mk(18,418,354,50,'故事语言','English、Chinese'), mk(18,468,354,54,'Auto-unlock','第 4 集起自动花 10 金币解锁'), mk(18,522,354,54,'VIP (test)','打开后所有集免费，测试开关'), mk(18,588,354,52,'Coin store','打开金币商店'), mk(18,640,354,52,'Reset all data','清空本机的金币、进度、收藏、账户'), mk(18,751,354,75,'Free listening (test)','测试用：重置为 30 分钟或立刻用完')]),
 '66-signin': ('登录', [mk(144,31,71,36,'Sign in','没登录时名字旁边是登录按钮'), mk(0,608,390,236,'登录弹层','在听的剧、金币和收藏跟着账户走'), mk(18,712,354,50,'Apple','通过 Apple 登录（原型里是模拟登录）'), mk(18,772,354,50,'Google','通过 Google 登录')]),
 '67-signed-in': ('登录后：用原名或改名', [mk(84,22,122,28,'账户名','登录后带出账户原来的名字（示例 Mia Carter），旁边出现笔'), mk(0,692,390,152,'已登录','登录后马上弹出：用原来的名字，也可以改一个'), mk(18,778,268,48,'名字框','默认填好原名，直接点 Done 就用它')]),
 '11-rewards': ('福利页', OLD['11-rewards']['marks']), '12-rewards-daily': ('每日任务', OLD['12-rewards-daily']['marks']),
 '51-rewards-new': ('新手福利', [mk(137,78,104,42,'New listener','5 项一次性任务，共 90 金币'), mk(273,88,85,22,'进度','已领几项'), mk(32,130,326,91,'可以领的','已经完成的任务排在最前面，直接 Claim'), mk(32,231,326,394,'其余任务','只留任务名和奖励，每条下面的说明去掉了')]),
 '65-coin-history': ('金币记录（展开）', OLD['65-coin-history']['marks']),
 '13-coin-store': ('金币商店', [m if m['n'] != 'VIP' else mk(*m['r'], 'VIP', '所有实时集免解锁、不用等；测试开关，不收费') for m in OLD['13-coin-store']['marks']]),
}
STEPS = [('新人引导', ['01-onboard-welcome', '02-ob-name', '03-ob-turn', '04-ob-end']),
 ('首页', ['04-home', '05-home-shelves', '06-home-more', '53-home-end', '26-mini-player']),
 ('搜索和分类', ['07-find-open', '08-find-results', '09-find-genre']),
 ('剧集详情', ['16-detail', '17-detail-synopsis', '18-detail-about', '15-detail-episodes', '19-detail-similar']),
 ('播放器', ['21-player', '22-sleep-timer', '23-episodes', '25-locked-episode', '42-unlock-sheet', '43-unlock-no-coins', '24-listening-mode']),
 ('选择点', ['27-choice-asking', '28-choice-typing', '29-choice-listening', '30-choice-speaking']),
 ('下一集', ['31-next-lines', '32-episode-2']),
 ('我的', ['60-me', '61-me-edit', '62-me-saved', '63-settings', '66-signin', '67-signed-in']),
 ('福利和金币', ['11-rewards', '12-rewards-daily', '51-rewards-new', '65-coin-history', '13-coin-store']),
 ('锁屏（真机截图）', ['45-lock-playback', '46-lock-your-move', '47-lock-hearing', '48-lock-writing'])]
os.makedirs('jpg', exist_ok=True)
for st, ids in STEPS:
    for i in ids:
        if os.path.exists(f'jpg/{i}.jpg'): continue
        if i in NEW: Image.open(f'shots/{i}.png').convert('RGB').save(f'jpg/{i}.jpg', quality=88, optimize=True)
        else: urllib.request.urlretrieve(OLD[i]['img'], f'jpg/{i}.jpg')
for i, (n, ms) in NEW.items():
    for m in ms: x, y, w, h = m['r']; assert 0 <= x and x + w <= 390 and 0 <= y and y + h <= 844, (i, m)
N = sum(len(ids) for _, ids in STEPS)
F = ImageFont.truetype('/System/Library/Fonts/Hiragino Sans GB.ttc', 20)
name = lambda i: NEW[i][0] if i in NEW else OLD[i]['name']
marks = lambda i: NEW[i][1] if i in NEW else OLD[i]['marks']
def comp(idx, ids):
    n = len(ids); four = n == 4 or n > 6
    if four: W, m, sw, sh, gap, cap = 1500, 18, 351, 760, 20, 43
    else: W, m, sw, sh, gap, cap = 1254, 20, 390, 844, 22, 48
    if n < 3: W = 2 * m + n * sw + (n - 1) * gap
    cols = 4 if four else 3; rows = (n + cols - 1) // cols
    H = m + rows * (sh + cap) + (rows - 1) * (10 if not four else 0)
    im = Image.new('RGB', (W, H), (245, 246, 248)); d = ImageDraw.Draw(im)
    for k, i in enumerate(ids):
        r, c = divmod(k, cols); x = m + c * (sw + gap); y = m + r * (sh + cap + (10 if not four else 0))
        sc = Image.open(f'jpg/{i}.jpg').convert('RGB').resize((sw * 2, sh * 2), Image.LANCZOS).resize((sw, sh), Image.LANCZOS)
        mask = Image.new('L', (sw * 2, sh * 2), 0); ImageDraw.Draw(mask).rounded_rectangle((0, 0, sw * 2 - 1, sh * 2 - 1), 48, fill=255); mask = mask.resize((sw, sh), Image.LANCZOS)
        im.paste(sc, (x, y), mask); t = name(i); w = d.textlength(t, font=F); d.text((x + (sw - w) / 2, y + sh + 10), t, font=F, fill=(58, 60, 70))
    fn = f'step{idx:02d}.jpg'; im.save(fn, quality=88, optimize=True); return fn, [W, H]
LOCK = ('https://storage.googleapis.com/waku-core-aicap/uploads/usr_4a6e5fb234d64da0a9429e519b299f07/f377aa9eeebb407ba13251b95d52fdf2/step12.jpg', [1500, 821])
steps = []
for k, (st, ids) in enumerate(STEPS, 1):
    if k == 10: steps.append({'k': k, 'step': st, 'img': None, 'size': LOCK[1], 'ids': ids}); continue
    fn, size = comp(k, ids); steps.append({'k': k, 'step': st, 'img': fn, 'size': size, 'ids': ids})
json.dump(steps, open('steps24.json', 'w'), ensure_ascii=False)
need = [f'jpg/{i}.jpg' for i in NEW if any(i in ids for _, ids in STEPS)] + [s['img'] for s in steps if s['img']]
if not os.path.exists('urls24.tsv'): print('screens', N, 'upload', len(need)); open('need.txt', 'w').write('\n'.join(need)); sys.exit(0)
urls = {i: OLD[i]['img'] for i in OLD}; urls.update(dict(l.rstrip('\n').split('\t') for l in open('urls24.tsv') if l.strip()))
data = [{'step': st, 'screens': [{'id': i, 'name': name(i), 'img': urls[i], 'marks': marks(i)} for i in ids]} for st, ids in STEPS]
v = open('viewer_cur.html').read(); a = v.index('var DATA=') + 9; b = v.index(';\nvar flat=')
v = v[:a] + json.dumps(data, ensure_ascii=False) + v[b:]
c = v.count('精简版 10 步 44 个界面'); assert c >= 1, c
v = v.replace('精简版 10 步 44 个界面', f'精简版 10 步 {N} 个界面'); open('viewer.html', 'w').write(v); print('viewer', len(v.encode()), 'screens', N)
SC = {1500: '0.679999', 1254: '0.813397', 842: '0.274347'}
rows = []
for s in steps:
    u, (w, h) = (urls['step%02d' % s['k']], s['size']) if s['img'] else LOCK
    ps = ''.join(f'<p><b>{html.escape(name(i))}</b>：{html.escape("、".join(m["n"] for m in marks(i)))}</p>' for i in s['ids'])
    rows.append(f'<tr><td vertical-align="top"><p><b>{s["k"]:02d}</b></p><p><b>{html.escape(s["step"])}</b></p></td><td vertical-align="top"><img href="{html.escape(u)}" width="{w}" height="{h}" scale="{SC[w]}"/></td><td vertical-align="top">{ps}</td></tr>')
tbl = ('<table><colgroup><col width="90"/><col width="470"/><col width="260"/></colgroup><thead><tr>' + ''.join(f'<th background-color="rgb(246,241,254)" vertical-align="top"><p><b>{t}</b></p></th>' for t in ('步骤', '界面截图（英文版）', '每个界面上的功能点')) + '</tr></thead><tbody>' + ''.join(rows) + '</tbody></table>')
open('table24.xml', 'w').write(tbl); print('table', len(tbl.encode()))
