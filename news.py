import pandas as pd
from jinja2 import Template
import json
import sys
import os
import datetime

# ==========================================
# 1. 基础配置与排序权重定义
# ==========================================
SHEET_URL = "https://docs.google.com/spreadsheets/d/1xPMH9Iv7EZpKAPyBjZDdUxny3R4Tb39lI43NYX3B0po/export?format=csv&gid=0"

CORE_COMPANIES = ['OpenAI', 'Google', 'Anthropic', 'Meta', '字节跳动', '阿里巴巴', '腾讯', '百度']
SECONDARY_COMPANIES = ['Kimi', 'MiniMax', '智谱', 'xAI', '可灵', 'DeepSeek', 'Apple', '美团']
SECONDARY_TITLE = "其余重点关注公司"

TOPIC_ORDER = ['技术迭代', '产品动态', '数据洞察', '行业洞察', '商业动态', '运营活动', '春节活动']

OTHER_PRIORITY = [
    'Perplexity', 'Character.ai', 'Midjourney', 'Pika', 'Runway', 
    'Suno', 'Luma', 'Grok', 'Mistral', 'Cohere', 'OpenClaw',
    'Microsoft', 'Apple', '英伟达', 'AMD', 'Intel', 'TSMC', 'Samsung', 'Amazon',
    'Tesla', 'Notion', 'Canva', 'Adobe', 'GitHub', 'Arc', 'Cursor', 'Groq',
    '特斯拉', '波士顿动力', '宇树', '智元', '银河', '星海图', 'Fiture', 'Figure', 
    'Sanctuary AI', '1X Technologies', 'Agility Robotics', '小红书', '森森'
]

def parse_date_for_sort(date_str):
    d_part = date_str.split('至')[1].strip() if '至' in date_str else date_str.strip()
    try:
        return datetime.datetime.strptime(d_part, '%Y/%m/%d')
    except:
        return datetime.datetime.min

def get_company_rank(c_val):
    if c_val in CORE_COMPANIES: return CORE_COMPANIES.index(c_val)
    if c_val in SECONDARY_COMPANIES: return len(CORE_COMPANIES) + SECONDARY_COMPANIES.index(c_val)
    return 999

def get_topic_rank(t_val):
    main_topic = t_val[0] if isinstance(t_val, list) and len(t_val) > 0 else t_val
    return TOPIC_ORDER.index(main_topic) if main_topic in TOPIC_ORDER else 99

def main():
    # 2. 数据读取与预处理
    try:
        df = pd.read_csv(SHEET_URL)
    except Exception as e:
        print(f"❌ 读取错误: {e}")
        if os.path.exists("data.csv"): df = pd.read_csv("data.csv")
        else: sys.exit(1)

    df.columns = [c.strip() for c in df.columns]
    
    df['日期'] = df['日期'].astype(str).str.strip()
    df = df[df['日期'] != ""]
    
    # 清洗关键“分类”列
    if '分类' in df.columns:
        df['分类'] = df['分类'].astype(str).str.strip()
    else:
        df['分类'] = ""
    
    name_map = {'字节': '字节跳动', '阿里': '阿里巴巴', 'Baidu': '百度', 'minimax': 'MiniMax', '智谱AI': '智谱', 'OpenAI ': 'OpenAI'}
    df['公司'] = df['公司'].replace(name_map)
    df['是否头条'] = pd.to_numeric(df['是否头条'], errors='coerce').fillna(0).astype(int)
    df = df.fillna("")
    
    df['话题_list'] = df['话题'].apply(lambda x: [i.strip() for i in str(x).replace(' ', '').split('、')] if x else [])
    df['公司_list'] = df['公司'].apply(lambda x: [i.strip() for i in str(x).split('、')] if x else [])
    
    all_individual_topics = set()
    for t_list in df['话题_list']: all_individual_topics.update(t_list)
    all_unique_topics = sorted(list(all_individual_topics))

    all_individual_companies = set()
    for c_list in df['公司_list']: all_individual_companies.update(c_list)
    all_unique_companies_clean = sorted(list(all_individual_companies), key=lambda x: x.encode('gbk') if isinstance(x, str) else x)

    def get_ymd(date_str):
        dt = parse_date_for_sort(date_str)
        return dt.year, dt.month
    df['year'], df['month'] = zip(*df['日期'].apply(get_ymd))

    df_exploded = df.explode('公司_list')
    
    all_dates = [str(d) for d in df['日期'].dropna().unique() if str(d).strip() != ""]
    all_dates.sort(key=parse_date_for_sort, reverse=True)

    # 3. 核心分发逻辑
    news_data_map = {}
    headlines_ai_map = {}
    headlines_browser_map = {}

    for date in all_dates:
        day_df_orig = df[df['日期'] == date].copy()
        headline_df = day_df_orig[day_df_orig['是否头条'] > 0].copy()
        
        if not headline_df.empty:
            headline_df['c_rank'] = headline_df['公司'].apply(get_company_rank)
            headline_df['t_rank'] = headline_df['话题_list'].apply(get_topic_rank)
            sorted_headlines = headline_df.sort_values(by=['是否头条', 'c_rank', 't_rank']).to_dict('records')
            
            ai_hl = []
            browser_hl = []
            for item in sorted_headlines:
                if item['分类'] in ['浏览器', '输入法']:
                    browser_hl.append(item)
                else:
                    ai_hl.append(item)
                    
            headlines_ai_map[date] = ai_hl
            headlines_browser_map[date] = browser_hl
        else:
            headlines_ai_map[date] = []
            headlines_browser_map[date] = []

        day_df_exp = df_exploded[df_exploded['日期'] == date].copy()
        news_data_map[date] = {}

        def sort_section_data(data_df, is_other=False):
            def calc_company_internal_score(c_name):
                if is_other: return OTHER_PRIORITY.index(c_name) if c_name in OTHER_PRIORITY else 999
                return get_company_rank(c_name)
            def calc_item_rank_score(row):
                val = row['是否头条']
                t_idx = get_topic_rank(row['话题_list'])
                return val if val > 0 else (1000 + t_idx)
            data_df['co_group_rank'] = data_df['公司_list'].apply(calc_company_internal_score)
            data_df['item_internal_rank'] = data_df.apply(calc_item_rank_score, axis=1)
            return data_df.sort_values(by=['co_group_rank', 'item_internal_rank']).to_dict('records')

        for company in CORE_COMPANIES:
            comp_df = day_df_exp[day_df_exp['FF_list' if 'FF_list' in day_df_exp.columns else '公司_list'] == company].copy()
            if not comp_df.empty: news_data_map[date][company] = sort_section_data(comp_df)
        sec_df = day_df_exp[day_df_exp['公司_list'].isin(SECONDARY_COMPANIES)].copy()
        if not sec_df.empty: news_data_map[date][SECONDARY_TITLE] = sort_section_data(sec_df)
        other_df = day_df_exp[~day_df_exp['公司_list'].isin(CORE_COMPANIES + SECONDARY_COMPANIES)].copy()
        if not other_df.empty: news_data_map[date]['行业新闻'] = sort_section_data(other_df, is_other=True)

    final_json_str = json.dumps(df.to_dict('records'), ensure_ascii=False)

    # ==========================================
    # 4. 读取独立的 HTML 模板文件进行编译渲染
    # ==========================================
    if not os.path.exists("template.html"):
        print("❌ 错误：未在当前目录下找到 template.html 模板文件！")
        sys.exit(1)
        
    with open("template.html", "r", encoding="utf-8") as tf:
        template_str = tf.read()

    html = Template(template_str).render(
        dates=all_dates, 
        news_data_map=news_data_map, 
        headlines_ai_map=headlines_ai_map, 
        headlines_browser_map=headlines_browser_map, 
        final_json_str=final_json_str, 
        all_companies_clean=all_unique_companies_clean,
        all_topics=all_unique_topics,
        SECONDARY_TITLE=SECONDARY_TITLE
    )
    
    with open("index.html", "w", encoding="utf-8") as f: f.write(html)
    print("✨ index.html 基于外部 template.html 模板重新编译成功！")

if __name__ == "__main__":
    main()
