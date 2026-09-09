import io
import re
import pandas as pd
import streamlit as st
import streamlit as st

# إخفاء الشريط العلوي بالكامل (Header)
st.markdown(
    """
    <style>
    header[data-testid="stHeader"] {
        visibility: hidden;
        height: 0%;
    }
    </style>
    """,
    unsafe_allow_html=True,

)

st.markdown(
    """
    <style>
    .stAppToolbar {
        visibility: hidden;
    }
    </style>
    """,
    unsafe_allow_html=True,
)
# ضبط إعدادات الصفحة
st.set_page_config(
    page_title="نظام تدقيق ومطابقة أجهزة Intune وسجل العهدة",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("🔍 نظام التدقيق والمطابقة الاحترافي الأجهزة (Intune vs Physical Audit)")
st.caption("مقارنة سجل الجرد الميداني للعهدة مع التقرير المركزي لـ Microsoft Intune وتصنيف المخاطر.")

# --- Functions (دوال مساعدة للذكاء والتنظيف) ---

def normalize_value(val):
    """تنظيف وتوحيد القيم لتجنب الفروق السطحية مثل المسافات والحروف الصغيرة/الكبيرة"""
    if pd.isna(val) or val is None:
        return ""
    val_str = str(val).strip()
    if val_str.lower() in ["nan", "none", "null", "<na>", "-", "n/a"]:
        return ""
    
    if re.match(r"^-?\d+\.0$", val_str):
        val_str = val_str[:-2]
        
    val_str = re.sub(r"\s+", " ", val_str)
    return val_str.upper()

# --- Sidebar Inputs ---

st.sidebar.header("⚙️ 1. رفع البيانات")
file1 = st.sidebar.file_uploader("رفع النظام المركزي / Intune Master Report", type=["xlsx", "csv"])
file2 = st.sidebar.file_uploader("رفع سجل الجرد الميداني للعهدة / Physical Audit File", type=["xlsx", "csv"])

if file1 and file2:
    df1 = pd.read_excel(file1) if file1.name.endswith("xlsx") else pd.read_csv(file1)
    df2 = pd.read_excel(file2) if file2.name.endswith("xlsx") else pd.read_csv(file2)

    df1.columns = df1.columns.astype(str).str.strip()
    df2.columns = df2.columns.astype(str).str.strip()

    st.sidebar.markdown("---")
    st.sidebar.subheader("🔑 2. اختيار معرف المطابقة (Serial Number)")

    def get_default_key_index(cols):
        for i, c in enumerate(cols):
            c_low = c.lower()
            if "serial" in c_low or "sn" in c_low:
                return i
        for i, c in enumerate(cols):
            c_low = c.lower()
            if any(k in c_low for k in ["device", "id", "asset", "host"]):
                return i
        return 0

    key_col1 = st.sidebar.selectbox("الرقم التسلسلي - نظام Intune:", options=df1.columns, index=get_default_key_index(df1.columns))
    key_col2 = st.sidebar.selectbox("الرقم التسلسلي - سجل الجرد الميداني:", options=df2.columns, index=get_default_key_index(df2.columns))

    use_secondary_key = st.sidebar.checkbox("🔗 استخدام مفتاح مركب (Serial + Hostname)")

    if use_secondary_key:
        cols_f1_sec = [c for c in df1.columns if c != key_col1]
        cols_f2_sec = [c for c in df2.columns if c != key_col2]
        key2_col1 = st.sidebar.selectbox("المعرف الثانوي - نظام Intune:", options=cols_f1_sec)
        key2_col2 = st.sidebar.selectbox("المعرف الثانوي - سجل الجرد الميداني:", options=cols_f2_sec)

        df1["_clean_key"] = df1[key_col1].apply(normalize_value) + " | " + df1[key2_col1].apply(normalize_value)
        df2["_clean_key"] = df2[key_col2].apply(normalize_value) + " | " + df2[key2_col2].apply(normalize_value)
    else:
        df1["_clean_key"] = df1[key_col1].apply(normalize_value)
        df2["_clean_key"] = df2[key_col2].apply(normalize_value)

    df1_clean = df1[df1["_clean_key"] != ""].copy()
    df2_clean = df2[df2["_clean_key"] != ""].copy()

    merged = pd.merge(df1_clean, df2_clean, on="_clean_key", how="outer", suffixes=("_Master", "_Audit"))

    st.sidebar.markdown("---")
    st.sidebar.subheader("🎯 3. ضبط المطابقة الحقلية (يدوياً)")

    ignore_cols_f1 = [key_col1, "_clean_key"] + ([key2_col1] if use_secondary_key else [])
    ignore_cols_f2 = [key_col2, "_clean_key"] + ([key2_col2] if use_secondary_key else [])

    cols_f1 = [c for c in df1.columns if c not in ignore_cols_f1]
    cols_f2 = [c for c in df2.columns if c not in ignore_cols_f2]

    mapping_pairs = []
    
    st.sidebar.caption("حدد العمود المقابل يدوياً من القائمة (جميع القوائم تبدأ افتراضياً بـ التجاهل):")
    for c2 in cols_f2:
        opts = ["[تجاهل هذا العمود]"] + cols_f1
        # تعيين الخيار الافتراضي دائماً عند الموضع 0 -> [تجاهل هذا العمود]
        selected_c1 = st.sidebar.selectbox(
            f"العمود المقابل لـ [{c2}] في الجرد:", 
            options=opts, 
            index=0, 
            key=f"map_{c2}"
        )
        if selected_c1 != "[تجاهل هذا العمود]":
            mapping_pairs.append((selected_c1, c2))

    # --- Process Comparisons & Categorize Severity ---

    discrepancies = []

    keys_in_master = set(df1_clean["_clean_key"])
    keys_in_audit = set(df2_clean["_clean_key"])

    for idx, row in merged.iterrows():
        key_val = row["_clean_key"]

        in_master = key_val in keys_in_master
        in_audit = key_val in keys_in_audit

        # حالة 1: جهاز موجود في الجرد الميداني وغير مسجل بـ Intune (خطورة عالية)
        if not in_master and in_audit:
            discrepancies.append({
                "مستوى الخطورة": "🔴 عالية (High)",
                "الرقم التسلسلي (Serial)": key_val,
                "الحقل المفحوص": "سجل وجود الجهاز",
                "بيانات نظام Intune": "غير مسجل بالنظام",
                "بيانات سجل الجرد الميداني": "موجود فعلياً بالعهدة",
                "نوع الخلل": "جهاز غير مسجل في النظام المركزي",
            })
            continue

        # حالة 2: جهاز مسجل بـ Intune وغير موجود بالجرد الميداني (خطورة عالية)
        if in_master and not in_audit:
            discrepancies.append({
                "مستوى الخطورة": "🔴 عالية (High)",
                "الرقم التسلسلي (Serial)": key_val,
                "الحقل المفحوص": "سجل وجود الجهاز",
                "بيانات نظام Intune": "مسجل بالنظام",
                "بيانات سجل الجرد الميداني": "غير موجود بالجرد الميداني",
                "نوع الخلل": "جهاز مفقود من الواقع العملي",
            })
            continue

        # حالة 3: اختلاف البيانات الحقلية بين النظام والسجل الميداني
        for c1, c2 in mapping_pairs:
            col_f1_name = f"{c1}_Master" if f"{c1}_Master" in row else c1
            col_f2_name = f"{c2}_Audit" if f"{c2}_Audit" in row else c2

            raw_val1 = row.get(col_f1_name)
            raw_val2 = row.get(col_f2_name)

            norm_val1 = normalize_value(raw_val1)
            norm_val2 = normalize_value(raw_val2)

            if norm_val1 != norm_val2:
                disp_col_name = f"{c1} (Intune) ↔ {c2} (Audit)"
                
                c2_lower = c2.lower()
                if any(k in c2_lower for k in ["owner", "user", "mail", "email"]):
                    severity = "🟠 متوسطة (Medium)"
                    err_type = "اختلاف بيانات الموظف المسؤول"
                else:
                    severity = "🟡 منخفضة (Low)"
                    err_type = "اختلاف في المسمى أو البيانات الثانوية"

                discrepancies.append({
                    "مستوى الخطورة": severity,
                    "الرقم التسلسلي (Serial)": key_val,
                    "الحقل المفحوص": disp_col_name,
                    "بيانات نظام Intune": str(raw_val1) if pd.notna(raw_val1) else "[فارغ]",
                    "بيانات سجل الجرد الميداني": str(raw_val2) if pd.notna(raw_val2) else "[فارغ]",
                    "نوع الخلل": err_type,
                })

    res_df = pd.DataFrame(discrepancies)

    # --- Dashboards & Visualization ---

    st.subheader("📊 مؤشرات قياس المطابقة وتقييم المخاطر")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("إجمالي الأجهزة المفحوصة", len(merged))
    
    high_risk_count = len(res_df[res_df["مستوى الخطورة"] == "🔴 عالية (High)"]) if not res_df.empty else 0
    med_risk_count = len(res_df[res_df["مستوى الخطورة"] == "🟠 متوسطة (Medium)"]) if not res_df.empty else 0
    
    m2.metric("مخاطر عالية (أجهزة مفقودة/غير مسجلة)", high_risk_count)
    m3.metric("مخاطر متوسطة (اختلاف موظفين/إيميلات)", med_risk_count)
    m4.metric("إجمالي الحالات غير المطابقة", len(res_df))

    st.markdown("---")

    # --- Tabs View ---
    tab1, tab2, tab3 = st.tabs(["🚨 قائمة الفروقات والفلترة حسب الخطورة", "🔍 البحث والتفاصيل لجهاز محدد", "📈 تحليل الأعمدة والأخطاء"])

    with tab1:
        if not res_df.empty:
            c_filter1, c_filter2 = st.columns(2)
            with c_filter1:
                filter_severity = st.selectbox("تصفية حسب مستوى الخطورة:", ["الكل", "🔴 عالية (High)", "🟠 متوسطة (Medium)", "🟡 منخفضة (Low)"])
            with c_filter2:
                filter_err_type = st.selectbox("تصفية حسب نوع الخلل:", ["الكل"] + list(res_df["نوع الخلل"].unique()))

            filtered_df = res_df.copy()
            if filter_severity != "الكل":
                filtered_df = filtered_df[filtered_df["مستوى الخطورة"] == filter_severity]
            if filter_err_type != "الكل":
                filtered_df = filtered_df[filtered_df["نوع الخلل"] == filter_err_type]

            st.dataframe(filtered_df, width="stretch", height=400)

            output = io.BytesIO()
            with pd.ExcelWriter(output, engine="openpyxl") as writer:
                filtered_df.to_excel(writer, sheet_name="تقرير_المطابقة_والمخاطر", index=False)

            st.download_button(
                label="📥 تنزيل تقرير التدقيق (Excel)",
                data=output.getvalue(),
                file_name="Intune_Audit_Severity_Report.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        else:
            st.success("🎉 جميع البيانات مطابقة تماماً دون وجود أي مخاطر أو اختلافات.")

    with tab2:
        st.subheader("🔎 استعلام تفصيلي لجهاز محدد")
        search_key = st.selectbox("اختر الرقم التسلسلي (Serial Number):", options=merged["_clean_key"].unique())
        
        if search_key:
            row_f1 = df1_clean[df1_clean["_clean_key"] == search_key]
            row_f2 = df2_clean[df2_clean["_clean_key"] == search_key]
            
            c_left, c_right = st.columns(2)
            with c_left:
                st.markdown("##### 📁 بيانات نظام Intune (Master)")
                if not row_f1.empty:
                    st.json(row_f1.drop(columns=["_clean_key"]).to_dict(orient="records")[0])
                else:
                    st.error("غير مسجل في النظام المركزي")
                    
            with c_right:
                st.markdown("##### 📁 بيانات سجل الجرد الميداني (Audit)")
                if not row_f2.empty:
                    st.json(row_f2.drop(columns=["_clean_key"]).to_dict(orient="records")[0])
                else:
                    st.error("غير موجود في سجل الجرد الميداني")

    with tab3:
        if not res_df.empty:
            st.subheader("📊 توزيع الحالات حسب مستوى الخطورة")
            sev_counts = res_df["مستوى الخطورة"].value_counts().reset_index()
            sev_counts.columns = ["مستوى الخطورة", "عدد الحالات"]
            st.bar_chart(data=sev_counts, x="مستوى الخطورة", y="عدد الحالات")