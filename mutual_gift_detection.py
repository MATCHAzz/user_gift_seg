import pandas as pd

# ============================================================
# 互刷行为检测脚本
# 数据源：仅使用 user_category_result.xlsx
#
# 逻辑：
#    在该人群中，找满足以下条件的互刷对：
#      - 用户 A 的 top1_anchor_id == 用户 B 的 user_id
#      - 用户 B 的 top1_anchor_id == 用户 A 的 user_id
#      即：A 的最多打赏对象是 B，B 的最多打赏对象也是 A
#
# 流程：
#   遍历用户 A
#    → A 的 top1 主播是 B？
#      → B 也是用户表里的人？
#        → B 的 top1 主播是 A？
#          → 记录互刷对 (A, B)，去重
# ============================================================

# ============================================================
# Step 1: 读取用户分类结果，筛出目标人群
# ============================================================
print("读取 user_category_result.xlsx ...")
user_df = pd.read_excel('user_category_result.xlsx')
print(f"  总用户数: {len(user_df)}")

# 对全量用户检测互刷行为
target = user_df.copy()
print(f"  参与互刷检测的用户数: {len(target)}")

# ============================================================
# Step 2: 在目标人群内检测互刷对
# 互刷定义：A.top1_anchor_id == B.user_id  且  B.top1_anchor_id == A.user_id
# ============================================================
# 构建 user_id -> top1_anchor_id 的映射（仅目标人群）
# 建映射表 uid_to_top1：把每个用户的 user_id → top1_anchor_id 存成字典，方便快速查找
uid_to_top1 = target.set_index('user_id')['top1_anchor_id'].to_dict()
target_user_set = set(target['user_id'])  # 用于后面快速判断「某个主播是不是也是用户」

mutual_pairs = []
seen = set()

for user_id, top1_anchor in uid_to_top1.items():
    # top1_anchor 必须也是目标人群中的某个 user_id
    if pd.isna(top1_anchor):
        continue
    top1_anchor = int(top1_anchor)
    if top1_anchor not in target_user_set:  # 判断 B 是否也是用户表中的人，否则不能反向打赏
        continue
    # 检查反向：B 的 top1_anchor_id 是否也是 A
    b_top1 = uid_to_top1.get(top1_anchor)  # 用字典查出 B 打赏最多的主播是谁 (b_top1) 用B作为key再去查
    if pd.isna(b_top1) if b_top1 is None else False:
        continue
    if b_top1 is not None and int(b_top1) == user_id:
        # 记录互刷对，并去重
        pair_key = tuple(sorted([user_id, top1_anchor]))
        if pair_key not in seen:
            seen.add(pair_key)
            mutual_pairs.append(pair_key)

print(f"\n  检测到互刷对数: {len(mutual_pairs)}")

if len(mutual_pairs) == 0:
    print("未检测到任何互刷行为。")
    exit()

# ============================================================
# Step 3: 整理互刷对明细，合入双方用户信息
# ============================================================
mutual_df = pd.DataFrame(mutual_pairs, columns=['user_id_A', 'user_id_B'])

# 需要展示的字段
info_cols = ['user_id', 'user_org', 'user_category', 'total_diamond',
             'top1_anchor_id', 'top1_anchor_diamond', 'top1_anchor_ratio',
             'top1_anchor_org', 'is_guild_anchor', 'is_guild_leader',
             'issame_user_top1anchor_org']
info_cols = [c for c in info_cols if c in user_df.columns]

# 合入用户 A 信息
mutual_df = mutual_df.merge(
    user_df[info_cols].rename(columns={'user_id': 'user_id_A'})
                      .add_prefix('A_').rename(columns={'A_user_id_A': 'user_id_A'}),
    on='user_id_A', how='left'
)

# 合入用户 B 信息
mutual_df = mutual_df.merge(
    user_df[info_cols].rename(columns={'user_id': 'user_id_B'})
                      .add_prefix('B_').rename(columns={'B_user_id_B': 'user_id_B'}),
    on='user_id_B', how='left'
)

# 双向打赏金额之和（A 打给 B + B 打给 A，即各自 top1_anchor_diamond）
mutual_df['total_mutual_diamond'] = (
    mutual_df['A_top1_anchor_diamond'].fillna(0) +
    mutual_df['B_top1_anchor_diamond'].fillna(0)
)

mutual_df = mutual_df.sort_values('total_mutual_diamond', ascending=False).reset_index(drop=True)

# ============================================================
# Step 4: 汇总统计
# ============================================================
mutual_user_ids = set(mutual_df['user_id_A']) | set(mutual_df['user_id_B'])
print(f"  涉及互刷的用户数: {len(mutual_user_ids)}")

print(f"\n互刷对明细（前10条）:")
preview_cols = ['user_id_A', 'user_id_B',
                'A_user_org', 'B_user_org',
                'A_top1_anchor_diamond', 'B_top1_anchor_diamond',
                'total_mutual_diamond',
                'A_user_category', 'B_user_category']
preview_cols = [c for c in preview_cols if c in mutual_df.columns]
print(mutual_df[preview_cols].head(10).to_string(index=False))

# ============================================================
# Step 5: 保存结果
# ============================================================
print("\n保存结果...")
mutual_df.to_excel('mutual_gift_pairs.xlsx', index=False)

print("\n完成！生成文件：")
print("  mutual_gift_pairs.xlsx  -> 互刷对明细（双方用户信息 + 双向打赏金额）")
