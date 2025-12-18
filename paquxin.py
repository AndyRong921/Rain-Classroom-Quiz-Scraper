import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import re
import os

# ================= 配置区域 =================
URL = "https://www.yuketang.cn/v2/web/index"
# 请确保路径正确
SAVE_PATH = "/xxxxxxx/xxxxxxx/xxxxxxx/.xlsx"
# ===========================================

def load_existing_data(filepath):
    if not os.path.exists(filepath):
        print("✨ 未检测到旧题库，将创建新文件。")
        return {}
    
    print(f"📂 正在加载旧题库: {filepath} ...")
    try:
        df = pd.read_excel(filepath).fillna("")
        existing_db = {}
        for _, row in df.iterrows():
            q_text = str(row['题目']).strip()
            existing_db[q_text] = row.to_dict()
        print(f"✅ 成功加载历史题目: {len(existing_db)} 道")
        return existing_db
    except Exception as e:
        print(f"⚠️ 读取旧文件失败，将重新开始: {e}")
        return {}

def clean_option_text(text):
    """
    清洗选项文本：去除开头的 A. B. 或 A B 等编号
    """
    if not text: return ""
    # 替换掉开头的 "A." "A " "A、" 这种格式
    return re.sub(r'^[A-F][\.\s、．]*', '', text).strip()

def run_interactive_spider():
    options = webdriver.ChromeOptions()
    options.add_experimental_option('excludeSwitches', ['enable-automation'])
    options.add_experimental_option('useAutomationExtension', False)
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    
    print("🚀 浏览器已启动...")
    question_db = load_existing_data(SAVE_PATH)
    
    driver.get(URL)

    print("\n" + "="*60)
    print("📢 【精准列对齐版 - 操作指南】")
    print("1. 登录 -> 进课程 -> 答题 -> 交卷。")
    print("2. 进入【查看试卷】详情页。")
    print("3. 回到这里按 【回车 (Enter)】，自动抓取。")
    print("="*60 + "\n")
    
    batch_count = 1
    while True:
        user_input = input(f"waiting... 请操作到【答案页面】后按回车 (输入 q 退出): ")
        if user_input.lower() == 'q': break

        if len(driver.window_handles) > 1:
            driver.switch_to.window(driver.window_handles[-1])

        print(f"   ⚡️ 正在第 {batch_count} 次抓取...")

        try:
            blocks = driver.find_elements(By.CLASS_NAME, "result_item")
            if not blocks:
                print("   ⚠️ 没找到题目，请确认你在【查看试卷】页面！")
                continue

            new_count = 0
            for block in blocks:
                try:
                    # 1. 提取题目
                    q_text_ele = block.find_element(By.CSS_SELECTOR, ".item-body h4")
                    q_text = q_text_ele.text.strip()
                    
                    if q_text in question_db:
                        continue

                    # ==========================================
                    # 💡 核心修复：防止选项重复抓取
                    # ==========================================
                    
                    # 策略：优先找最精准的 .radioText / .checkboxText
                    # 这些类名通常只包含选项内容，没有多余的标签
                    opt_eles = block.find_elements(By.CSS_SELECTOR, ".radioText, .checkboxText")
                    
                    # 如果上面没找到（兼容旧版或者特殊题型），再找 ElementUI 的通用标签
                    if not opt_eles:
                        opt_eles = block.find_elements(By.CSS_SELECTOR, ".el-radio__label, .el-checkbox__label")

                    # 提取并清洗文本 (防止抓到 "A. 选项内容" 这种带标号的)
                    opts = []
                    for o in opt_eles:
                        txt = o.text.strip()
                        if txt:
                            # 进一步清洗：去掉可能的重复前缀
                            clean_txt = clean_option_text(txt)
                            opts.append(clean_txt)
                    
                    # ==========================================

                    # 3. 提取答案
                    full_text = block.text
                    ans_match = re.search(r"正确答案[：:]\s*([A-Za-z\s,\u4e00-\u9fa5]+)", full_text)
                    raw_ans = ans_match.group(1).replace(" ", "").replace(",", "").strip() if ans_match else "未知"

                    item_data = {"题目": q_text}
                    # Excel 表头准备
                    labels = ['A', 'B', 'C', 'D', 'E', 'F']
                    
                    # --- 判断题型逻辑 ---
                    is_judgment = False
                    # 如果只有2个选项，且包含"正确/错误"，判定为判断题
                    if len(opts) == 2:
                        opt_str = "".join(opts)
                        if "正确" in opt_str or "错误" in opt_str or "对" in opt_str or "错" in opt_str:
                            is_judgment = True

                    if is_judgment:
                        # 判断题：答案转中文，选项列清空
                        if "A" in raw_ans or "正确" in raw_ans or "对" in raw_ans:
                            item_data["答案"] = "正确"
                        else:
                            item_data["答案"] = "错误"
                        
                        # 选项列全空
                        for label in labels:
                            item_data[label] = ""

                    else:
                        # 单选/多选：按实际数量填充
                        item_data["答案"] = raw_ans
                        
                        for i, label in enumerate(labels):
                            if i < len(opts):
                                # 填入对应的选项
                                item_data[label] = opts[i]
                            else:
                                # 超过选项数量的列，填空 (比如只有ABCD，那EF就空着)
                                item_data[label] = ""

                    question_db[q_text] = item_data
                    new_count += 1
                        
                except Exception as e:
                    # print(f"单题跳过: {e}") 
                    continue
            
            print(f"   ✅ 抓取成功！本轮【新增】: {new_count} 题 | 题库总计: {len(question_db)} 题")
            
            if new_count > 0:
                save_to_excel(question_db)
            else:
                print("   💤 本页题目都已存在。")
            
            print("-" * 40)
            batch_count += 1

        except Exception as e:
            print(f"   ❌ 全局错误: {e}")

    print("程序结束。")
    driver.quit()

def save_to_excel(data):
    try:
        df = pd.DataFrame(data.values())
        cols = ["题目", "答案", "A", "B", "C", "D", "E", "F"]
        existing_cols = [c for c in cols if c in df.columns]
        df = df[existing_cols]
        
        df.to_excel(SAVE_PATH, index=False)
        print(f"📁 文件已保存更新: {SAVE_PATH}")
    except Exception as e:
        print(f"❌ 保存失败: {e}")

if __name__ == "__main__":
    run_interactive_spider()
