import pandas as pd
import numpy as np

# ============================================================
# 配置区：如有公会主播列表，填入文件名和列名
# ============================================================
GUILD_ANCHOR_FILE = None       # 例如 '公会主播id.xlsx'，没有则填 None
GUILD_ANCHOR_COL  = 'anchor_id'  # 公会主播表中的 anchor_id 列名

# ============================================================
# Step 1: 读取数据
# ============================================================
print("读取公会长表...")
guild_leaders = pd.read_excel('公会长id.xlsx')
guild_leader_set = set(guild_leaders['user_id'])
print(f"  公会长人数: {len(guild_leader_set)}")

print("读取行为数据表（文件较大，请稍候）...")
df = pd.read_excel('ua_behavior_merged_may_org.xlsx',
                   sheet_name='ua_behavior_merged_may')
print(f"  行为数据行数: {len(df)}")

# 公会主播集合：如有外部表则读取，否则用行为表中 org_type 为普通公会/内容公会的 anchor_id 推导
# 口径：anchor_id 对应的 org_type 属于「普通公会」或「内容公会」的才算公会主播
GUILD_ORG_TYPES = {'普通公会', '内容公会'}

if GUILD_ANCHOR_FILE:
    guild_anchors = pd.read_excel(GUILD_ANCHOR_FILE)
    guild_anchor_set = set(guild_anchors[GUILD_ANCHOR_COL])
    print(f"  公会主播人数（外部表）: {len(guild_anchor_set)}")
else:
    # 用行为表推导：anchor_id 对应的 org_type 在「普通公会/内容公会」中 => 该 anchor 属于公会
    guild_anchor_set = set(
        df[df['org_type'].isin(GUILD_ORG_TYPES)]['anchor_id']
    )
    print(f"  公会主播人数（从行为表推导，org_type=普通公会/内容公会）: {len(guild_anchor_set)}")

# ============================================================
# Step 2: 按 user_id 聚合计算分类所需指标
# ============================================================
print("\n计算用户级指标...")

# 2-1 总打赏金额
user_total = df.groupby('user_id')['total_diamond_fee'].sum().rename('total_diamond')

# 2-2 Top1 主播打赏占比
anchor_diamond = df.groupby(['user_id', 'anchor_id'])['total_diamond_fee'].sum().reset_index()
top1 = anchor_diamond.sort_values('total_diamond_fee', ascending=False) \
                      .groupby('user_id').first().reset_index()
top1 = top1.rename(columns={'total_diamond_fee': 'top1_anchor_diamond',
                             'anchor_id': 'top1_anchor_id'})

# 2-3 单一公会打赏占比（仅统计 org_type 为普通公会/内容公会的打赏）
df_org = df[df['org_type'].isin(GUILD_ORG_TYPES)].copy()
org_diamond = df_org.groupby(['user_id', 'org_id'])['total_diamond_fee'].sum().reset_index()
top1_org = org_diamond.sort_values('total_diamond_fee', ascending=False) \
                       .groupby('user_id').first().reset_index()
top1_org = top1_org.rename(columns={'total_diamond_fee': 'top1_org_diamond',
                                    'org_id': 'top1_org_id'})

# 2-4 Top3 主播打赏合计 & 是否属于同一公会
# 取每个 user 打赏前3的 anchor
top3 = anchor_diamond.sort_values('total_diamond_fee', ascending=False) \
                      .groupby('user_id').head(3).reset_index(drop=True)

# 给 top3 主播关联 org_id（仅取 org_type 为普通公会/内容公会的记录，取 first）
anchor_org_map = df[df['org_type'].isin(GUILD_ORG_TYPES)].groupby('anchor_id')['org_id'].first()
top3['org_id'] = top3['anchor_id'].map(anchor_org_map)

# 判断 Top3 是否跨公会：
# 只有当 Top3 主播「全部属于同一个公会（org_id 相同且非空）」才算不跨公会
# 只要有任意一个主播公会为空（独立主播）或属于不同公会，均视为跨公会
def is_cross_org(org_series):
    valid = org_series.dropna()
    if len(valid) == len(org_series) and valid.nunique() == 1:
        return False   # 全部属于同一公会，不跨
    return True        # 有空值或有多个不同公会，算跨

top3_stats = top3.groupby('user_id').agg(
    top3_diamond=('total_diamond_fee', 'sum'),
).reset_index()
top3_cross = top3.groupby('user_id')['org_id'].apply(is_cross_org).reset_index()
top3_cross.columns = ['user_id', 'top3_cross_org']
top3_stats = top3_stats.merge(top3_cross, on='user_id', how='left')

# ============================================================
# Step 3: 合并所有指标
# ============================================================
user_df = user_total.reset_index()
user_df = user_df.merge(top1[['user_id', 'top1_anchor_diamond', 'top1_anchor_id']], on='user_id', how='left')
user_df = user_df.merge(top1_org[['user_id', 'top1_org_diamond', 'top1_org_id']], on='user_id', how='left')
user_df = user_df.merge(top3_stats, on='user_id', how='left')

# 计算占比
user_df['top1_anchor_ratio'] = user_df['top1_anchor_diamond'] / user_df['total_diamond']
user_df['top1_org_ratio']    = user_df['top1_org_diamond']    / user_df['total_diamond']
user_df['top3_ratio']        = user_df['top3_diamond']        / user_df['total_diamond']

# 是否是公会长
user_df['is_guild_leader'] = user_df['user_id'].isin(guild_leader_set)

# 是否公会主播：user_id 出现在 anchor_id 中，且该 anchor_id 对应 org_type 为普通公会/内容公会
user_df['is_guild_anchor'] = user_df['user_id'].isin(guild_anchor_set)

print(f"  用户总数: {len(user_df)}")

# ============================================================
# Step 4: 打分类标签（优先级从高到低）
# ============================================================
print("打分类标签...")

def classify(row):
    td   = row['total_diamond']
    t1r  = row['top1_anchor_ratio'] if pd.notna(row['top1_anchor_ratio']) else 0
    orgr = row['top1_org_ratio']    if pd.notna(row['top1_org_ratio'])    else 0
    t3r  = row['top3_ratio']        if pd.notna(row['top3_ratio'])        else 0

    # 1. 公会长
    if row['is_guild_leader']:
        return '公会长'

    # 2. 大哥：非公会长；Top1主播占比≥80%；总打赏≥10000
    if t1r >= 0.8 and td >= 10000:
        return '大哥'

    # 3. 强绑定粉丝（高/中/低价值）：非公会长；Top1主播占比≥80%
    if t1r >= 0.8:
        if td >= 5000:
            return '强绑定粉丝-高价值'
        elif td >= 1000:
            return '强绑定粉丝-中价值'
        else:
            return '强绑定粉丝-低价值'

    # 4. 公会赞助商：非公会长/大哥/强绑定粉丝；单一公会占比≥80%；总打赏≥10000
    if orgr >= 0.8 and td >= 10000:
        return '公会赞助商'

    # 5. 公会粉丝：非公会长/大哥/强绑定粉丝；单一公会占比≥80%；总打赏<10000
    if orgr >= 0.8 and td < 10000:
        return '公会粉丝'

    # 6. 公会主播：不属于以上类别；自身 anchor_id 对应的 org_type 为普通公会/内容公会
    if row['is_guild_anchor']:
        return '公会主播'

    # 7. Top3跨公会集中型大R：总打赏≥10000；Top3占比≥80%；Top3主播跨公会
    if td >= 10000 and t3r >= 0.8 and row['top3_cross_org']:
        return 'Top3跨公会集中型大R'

    # 8. 真分散型大R：总打赏≥10000；Top3占比<80%
    if td >= 10000 and t3r < 0.8:
        return '真分散型大R'

    # 9. 中价值其他用户：总打赏 1000~9999
    if 1000 <= td < 10000:
        return '中价值其他用户'

    # 10. 低价值其他用户：总打赏<1000
    if td < 1000:
        return '低价值其他用户'
    
    return '其他大R'

user_df['user_category'] = user_df.apply(classify, axis=1)

# ============================================================
# Step 5: 统计汇总
# ============================================================
print("\n===== 用户分类分布 =====")
summary = user_df.groupby('user_category').agg(
    人数=('user_id', 'count'),
    总打赏=('total_diamond', 'sum'),
    人均打赏=('total_diamond', 'mean'),
    打赏中位数=('total_diamond', 'median'),
).reset_index()
summary['人数占比'] = (summary['人数'] / summary['人数'].sum() * 100).round(2)
summary['消费占比'] = (summary['总打赏'] / summary['总打赏'].sum() * 100).round(2)
summary = summary.sort_values('总打赏', ascending=False)
print(summary.to_string(index=False))

# ============================================================
# Step 6: 将标签回写到原始明细表
# ============================================================
print("\n将标签回写到原始行为明细表...")
label_map = user_df.set_index('user_id')['user_category']
df['user_category'] = df['user_id'].map(label_map)

# ============================================================
# Step 7: 保存结果
# ============================================================
print("保存结果...")
# 用户维度汇总（含所有指标+分类）
user_df.to_excel('user_category_result.xlsx', index=False)
# 原始明细+分类标签
df.to_excel('ua_behavior_merged_may_labeled.xlsx', index=False)
# 分类统计摘要
summary.to_excel('user_category_summary.xlsx', index=False)

print("\n完成！生成文件：")
print("  user_category_result.xlsx         -> 用户维度汇总 + 分类标签")
print("  ua_behavior_merged_may_labeled.xlsx -> 原始明细行 + user_category 列")
print("  user_category_summary.xlsx         -> 分类统计摘要")
