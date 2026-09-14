"""Render article-native charts/cards. No participant calls or experiment mutations.
Run: uv run --no-project --with matplotlib python render_figures.py
"""
from pathlib import Path
import json, hashlib
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Circle, FancyArrowPatch
from matplotlib import font_manager

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
DATA=ROOT/'.experiment/v2/interim-pre-amendment-balanced.json'
BG='#fffdf8'; INK='#243640'; MUTED='#67777c'; TEAL='#16756f'; CORAL='#bf5a3d'; PALE='#e5f0ef'; PEACH='#fae9df'; LINE='#d7dfdc'
fp=font_manager.FontProperties(fname='/System/Library/Fonts/Hiragino Sans GB.ttc')
plt.rcParams.update({'font.family':fp.get_name(),'font.size':15,'axes.unicode_minus':False,'svg.fonttype':'none','savefig.facecolor':BG})

def canvas(w,h):
 f=plt.figure(figsize=(w,h),facecolor=BG); a=f.add_axes([0,0,1,1]); a.set(xlim=(0,1),ylim=(0,1));a.axis('off');return f,a

def txt(a,x,y,s,size=17,color=INK,weight='normal',ha='left',va='top',**kw):
 return a.text(x,y,s,fontsize=size,color=color,weight=weight,ha=ha,va=va,linespacing=1.7,**kw)
def box(a,x,y,w,h,fc=PALE):
 a.add_patch(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=0.012,rounding_size=0.018',fc=fc,ec='none'))
def arrow(a,p,q,color=MUTED):a.add_patch(FancyArrowPatch(p,q,arrowstyle='-|>',mutation_scale=18,color=color,lw=1.5))
def save(f,name):
 for ext in ('png','svg'):f.savefig(HERE/f'{name}.{ext}',dpi=150)
 plt.close(f)

raw=json.loads(DATA.read_text()); arms=['S','S+C','F3','F5','F7']; names=['单模型','单模型＋资料','三专家','五专家','七专家']; colors=[MUTED,TEAL,'#d69c82','#c97958',CORAL]
f,a=canvas(8,10)
txt(a,.07,.96,'专家增加，结果没有一路变好',24,weight='bold')
txt(a,.07,.903,'真实仓库实验 · 已完整完成的16题 · 每组48次',13,color=MUTED)
for bottom,height,key,title,lim in [(0.535,.29,'passed','通过次数 / 48',48),(0.14,.29,'mean_calls','平均模型调用 / 次',240)]:
 ax=f.add_axes([.33,bottom,.58,height],facecolor=BG)
 vals=[raw['per_arm'][k][key] for k in arms]
 ax.barh(range(5),vals,color=colors,height=.51)
 ax.set_yticks(range(5),names,fontsize=18);ax.invert_yaxis();ax.set_xlim(0,lim*1.14)
 ax.set_xticks([0,24,48] if key=='passed' else [0,80,160,240]); ax.tick_params(axis='both',length=0,labelcolor=MUTED,labelsize=15)
 ax.set_axisbelow(True);ax.grid(axis='x',color=LINE,linewidth=.7)
 for spine in ax.spines.values():spine.set_visible(False)
 for i,v in enumerate(vals):ax.text(v+lim*.025,i,f'{v:.0f}' if key=='passed' else f'{v:.1f}',va='center',fontsize=18,color=INK)
 txt(a,.07,bottom+height+.035,title,16,weight='bold')
txt(a,.07,.076,'阶段性描述：按执行进度形成的子集，非完整24题。',12,color=MUTED)
txt(a,.07,.042,'含争议任务原始评分；调用量不等于费用或耗时。',12,color=MUTED)
save(f,'01-committee')

f,a=canvas(8,8)
txt(a,.07,.955,'一个 now，两种“现在几点”',24,weight='bold')
txt(a,.07,.89,'真实接口争议 · 解释用伪代码',13,color=MUTED)
box(a,.065,.49,.87,.315,PALE)
a.add_patch(Circle((.17,.70),.047,transform=a.transAxes,fill=False,ec=TEAL,lw=2))
a.plot([.17,.17,.19],[.735,.70,.683],color=TEAL,lw=2)
txt(a,.27,.755,'传一张“此刻时间”的纸条',20,weight='bold')
txt(a,.105,.624,'now = 1000\n使用时直接读取这个数值',17)
txt(a,.105,.525,'隐藏测试采用这种约定',13,color=TEAL)
box(a,.065,.11,.87,.315,PEACH)
a.add_patch(Circle((.17,.32),.047,transform=a.transAxes,fill=False,ec=CORAL,lw=2))
txt(a,.17,.32,'?',24,color=CORAL,ha='center',va='center')
txt(a,.27,.375,'给一个“问时间”的方法',20,weight='bold')
txt(a,.105,.244,'now = () => 1000\n使用时调用 now() 获取时间',17)
txt(a,.105,.145,'13个候选采用这种理解',13,color=CORAL)
txt(a,.07,.055,'任务书没有明确类型：原始失败保留，歧义另做分析。',12,color=MUTED)
save(f,'04-clock')

f,a=canvas(8,7.5)
txt(a,.07,.95,'小模型＋方法，可以跨过一档',23,weight='bold')
txt(a,.07,.88,'WikiSkill 论文 · 五项基准平均准确率',14,color=MUTED)
ax=f.add_axes([.35,.30,.55,.45],facecolor=BG)
labels=['9B 无技能','9B＋技能','27B 无技能','27B＋技能'];vals=[29.9,47.4,39.4,63.3]
ax.barh(range(4),vals,color=[MUTED,TEAL,MUTED,TEAL],height=.5)
ax.set_yticks(range(4),labels,fontsize=17);ax.invert_yaxis();ax.set_xlim(0,75);ax.set_xticks([0,20,40,60]);ax.set_xticklabels(['0%','20%','40%','60%']);ax.grid(axis='x',color=LINE);ax.set_axisbelow(True);ax.tick_params(length=0,labelcolor=MUTED)
for sp in ax.spines.values():sp.set_visible(False)
for i,v in enumerate(vals):ax.text(v+1.5,i,f'{v}%',va='center',fontsize=16,color=INK)
box(a,.07,.13,.86,.085)
txt(a,.5,.173,'47.4% > 39.4%   ｜   但 47.4% < 63.3%',17,color=TEAL,weight='bold',ha='center',va='center')
txt(a,.07,.084,'9B：Qwen-3.5　27B：Qwen-3.6；不同模型代际。',11,color=MUTED)
txt(a,.07,.043,'外部论文表1；三次技能演化的测试均值，非自家实验。',11,color=MUTED)
save(f,'06-wikiskill')

f,a=canvas(8,9)
txt(a,.07,.96,'路标和计时器，也得检查',25,weight='bold')
box(a,.065,.51,.87,.365,PALE)
txt(a,.1,.837,'同一段历史，改一句状态提示',19,weight='bold')
txt(a,.1,.766,'旧：No deliver yet',16)
arrow(a,(.12,.699),(.19,.699));txt(a,.23,.699,'模型继续等待',18,color=CORAL,va='center')
txt(a,.1,.628,'新：只是未记录交付，准备好即可交付',15)
arrow(a,(.12,.565),(.19,.565));txt(a,.23,.565,'模型调用交付工具',18,color=TEAL,va='center')
box(a,.065,.115,.87,.33,PEACH)
txt(a,.1,.409,'Docker 客户端超时之后',19,weight='bold')
txt(a,.1,.34,'客户端',15);a.plot([.29,.58],[.325,.325],color=CORAL,lw=3);txt(a,.64,.325,'已超时',16,color=CORAL,va='center')
txt(a,.1,.261,'容器',15);arrow(a,(.29,.246),(.8,.246),CORAL);txt(a,.47,.212,'仍在运行',16,color=CORAL)
txt(a,.1,.159,'看到部分测试通过 ≠ 整套验收已经完成',14,weight='bold')
txt(a,.07,.072,'上：仅一对响应诊断，没有执行返回的工具。',12,color=MUTED)
txt(a,.07,.038,'下：四条超时记录；卡住原因未由此确定。',12,color=MUTED)
save(f,'08-harness')

f,a=canvas(8,7.5)
txt(a,.07,.95,'第一周变好了，第二周呢？',24,weight='bold')
txt(a,.07,.885,'回声对 / 天 · 同一任务在多个入口留下重复记录',13,color=MUTED)
ax=f.add_axes([.13,.36,.77,.39],facecolor=BG)
v=[14.4,3.57,13.0]; ax.bar(range(3),v,color=[MUTED,TEAL,CORAL],width=.48)
ax.set_xticks(range(3),['预设基线\n约30天','修改后第1周\n7天','随后第2周\n7天'],fontsize=13)
ax.set_ylim(0,18);ax.set_yticks([0,5,10,15]);ax.grid(axis='y',color=LINE);ax.set_axisbelow(True);ax.tick_params(length=0,labelcolor=MUTED)
for sp in ax.spines.values():sp.set_visible(False)
for i,n in enumerate(v):ax.text(i,n+.45,f'{n:.2f}',ha='center',fontsize=20,color=INK,weight='bold')
box(a,.07,.14,.86,.105,PEACH)
txt(a,.5,.194,'按“不回升”判据：第二周未通过',18,color=CORAL,weight='bold',ha='center',va='center')
txt(a,.07,.095,'91对中，76对集中一天；不能删掉爆发日改写结果。',12,color=MUTED)
txt(a,.07,.05,'配对数不是用户请求数；基线复算约14.34，图用预设14.4。',11,color=MUTED)
save(f,'09-memory')

(HERE/'chart-data.json').write_text(json.dumps({'interim':raw,'interim_source_sha256':hashlib.sha256(DATA.read_bytes()).hexdigest(),'wikiskill':{'source':'https://arxiv.org/html/2608.27454v1#S4.SS2','table':1,'models':['Qwen-3.5-9B','Qwen-3.6-27B'],'no_skill':[29.9,39.4],'wikiskill':[47.4,63.3]},'echo':{'pre_fixed_baseline':14.4,'recomputed_baseline_approx':14.34,'week1':3.57,'week2':13.0,'unit':'matched hook-cli pairs/day; not independent requests'}},ensure_ascii=False,indent=2)+'\n')
