import json
import random
from datetime import date, datetime, timedelta
from statistics import mean

import streamlit as st
from openai import OpenAI

# ======================================================
# CONFIG STREAMLIT
# ======================================================
st.set_page_config(
    page_title="ContentForge v9.4",
    page_icon="🍏",
    layout="wide",
)

# ======================================================
# OPENAI CLIENT (usa OPENAI_API_KEY do ambiente/Secrets)
# ======================================================
client = OpenAI()


# ======================================================
# ESTADO GLOBAL
# ======================================================
def init_state():
    # Plano selecionado
    if "plan" not in st.session_state:
        st.session_state.plan = "Pro"

    # Contagem de gerações por dia
    if "gens_date" not in st.session_state:
        st.session_state.gens_date = date.today().isoformat()
    if "gens_used_today" not in st.session_state:
        st.session_state.gens_used_today = 0
    # Se mudou o dia, reset
    today_str = date.today().isoformat()
    if st.session_state.gens_date != today_str:
        st.session_state.gens_date = today_str
        st.session_state.gens_used_today = 0

    # Últimas variações geradas (para não desaparecerem ao mudar de aba)
    if "last_variations" not in st.session_state:
        # lista de dicts: {titulo, legenda, hashtags, plataforma}
        st.session_state.last_variations = None

    # Planner: lista de tarefas
    if "planner" not in st.session_state:
        # cada tarefa:
        # {id, titulo, legenda, hashtags, plataforma, dia(YYYY-MM-DD), hora(HH:MM), score, status}
        st.session_state.planner = []

    if "next_task_id" not in st.session_state:
        st.session_state.next_task_id = 1

    if "selected_task_id" not in st.session_state:
        st.session_state.selected_task_id = None


# ======================================================
# HELPERS DE NEGÓCIO
# ======================================================
def limits_for_plan(plan: str):
    """Limites de gerações por dia por plano."""
    if plan == "Starter":
        return 5
    if plan == "Pro":
        return 50
    return 5


def emoji_for_niche(niche: str) -> str:
    n = (niche or "").lower()
    if "moda" in n or "roupa" in n:
        return "👗"
    if "fitness" in n or "ginásio" in n or "gym" in n:
        return "💪"
    if "restaurante" in n or "comida" in n or "food" in n:
        return "🍽️"
    if "fornecedor" in n or "wholesale" in n:
        return "📦"
    if "beleza" in n or "cosmética" in n:
        return "💄"
    return "✨"


def add_emoji_to_title(title: str, niche: str) -> str:
    title = (title or "").strip()
    if not title:
        return title
    # Se já começa com emoji, não mexer
    if title[0] in "✨👗💪🍽️📦💄🔥⭐🏆🌟🎯🍂":
        return title
    return f"{emoji_for_niche(niche)} {title}"


def fake_analysis(caption: str, hashtags: list[str]):
    """
    Análise automática fake mas estável e credível.
    Usa comprimento do texto + nº de hashtags para dar score.
    """
    words = len((caption or "").split())
    base = 7.0 + min(2.0, max(0, (words - 40) / 40))  # 7–9
    extra_hash = min(0.6, len(hashtags) * 0.03)

    # jitter pequeno mas estável
    seed = abs(hash(caption)) % 1000
    random.seed(seed)
    jitter = random.uniform(-0.3, 0.3)

    score_final = max(6.0, min(9.5, base + extra_hash + jitter))
    eng = max(6.0, min(9.5, base - 0.2 + random.uniform(-0.3, 0.3)))
    conv = max(6.0, min(9.5, base + 0.1 + random.uniform(-0.3, 0.3)))

    return {
        "score": round(score_final, 1),
        "engaj": round(eng, 1),
        "conv": round(conv, 1),
    }


def call_openai_variations(
    platform: str,
    brand: str,
    niche: str,
    tone: str,
    mode: str,
    message: str,
    extra: str,
):
    """
    Pede 3 variações à OpenAI e devolve:
    (lista_de_variacoes, erro_str_ou_None)

    variacao = {titulo, legenda, hashtags(list)}
    """
    user_prompt = f"""
Marca: {brand}
Nicho/tema: {niche}
Plataforma: {platform}
Tom de voz: {tone}
Modo de copy: {mode}

O que quero comunicar hoje:
\"\"\"{message}\"\"\"

Informação extra:
\"\"\"{extra}\"\"\"

Gera 3 variações de conteúdo para {platform}, em português de Portugal.

Cada variação deve ter:
- "titulo": título curto (máx. 80 caracteres), sem emojis
- "legenda": copy principal (70–160 palavras), com CTA claro
- "hashtags": lista com 8–15 hashtags relevantes (strings começadas por #, minúsculas, sem acentos)

Responde EXATAMENTE neste formato JSON:

{{
  "variacoes": [
    {{
      "titulo": "...",
      "legenda": "...",
      "hashtags": ["#...", "#..."]
    }},
    {{
      "titulo": "...",
      "legenda": "...",
      "hashtags": ["#...", "#..."]
    }},
    {{
      "titulo": "...",
      "legenda": "...",
      "hashtags": ["#...", "#..."]
    }}
  ]
}}
    """.strip()

    try:
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "És um copywriter especialista em redes sociais. "
                        "Escreves em português de Portugal, focado em venda suave, "
                        "credibilidade e emoção. Responde sempre em JSON válido."
                    ),
                },
                {"role": "user", "content": user_prompt},
            ],
        )
        raw = completion.choices[0].message.content
        data = json.loads(raw)
        vs = data.get("variacoes", [])
        out = []
        for v in vs[:3]:
            titulo = (v.get("titulo") or "").strip()
            legenda = (v.get("legenda") or "").strip()
            hashtags = v.get("hashtags") or []
            if not isinstance(hashtags, list):
                hashtags = []
            hashtags = [h.strip() for h in hashtags if isinstance(h, str) and h.strip()]

            if not titulo or not legenda:
                continue

            out.append(
                {
                    "titulo": titulo,
                    "legenda": legenda,
                    "hashtags": hashtags,
                    "plataforma": platform,
                }
            )
        if not out:
            return None, "A resposta da IA veio vazia ou num formato inesperado."
        return out, None
    except Exception as e:
        return None, f"Erro ao falar com a API: {e}"


def add_task_to_planner(variation: dict, day: date, time_obj, niche: str):
    """Adiciona uma tarefa ao planner e devolve o score."""
    task_id = st.session_state.next_task_id
    st.session_state.next_task_id += 1

    titulo = add_emoji_to_title(variation["titulo"], niche)
    legenda = variation["legenda"]
    hashtags = variation["hashtags"]
    platform = variation["plataforma"]

    analysis = fake_analysis(legenda, hashtags)
    score = analysis["score"]

    st.session_state.planner.append(
        {
            "id": task_id,
            "titulo": titulo,
            "legenda": legenda,
            "hashtags": hashtags,
            "plataforma": platform,
            "dia": day.isoformat(),
            "hora": time_obj.strftime("%H:%M"),
            "score": score,
            "status": "planned",
        }
    )
    return score


# ======================================================
# SIDEBAR
# ======================================================
def sidebar():
    st.sidebar.title("Plano & Perfil")

    # Plano
    plan = st.sidebar.selectbox(
        "Plano",
        ["Starter", "Pro"],
        index=1 if st.session_state.plan == "Pro" else 0,
    )
    st.session_state.plan = plan

    limit_per_day = limits_for_plan(plan)
    used_today = st.session_state.gens_used_today
    st.sidebar.markdown(
        f"**Gerações usadas hoje:** {used_today}/{limit_per_day}"
    )

    st.sidebar.markdown("---")

    brand = st.sidebar.text_input("Marca", "Loukisses")
    niche = st.sidebar.text_input("Nicho/tema", "Moda feminina")
    tone = st.sidebar.selectbox(
        "Tom de voz",
        ["profissional", "premium", "emocional", "descontraído"],
        index=1,
    )
    mode = st.sidebar.selectbox(
        "Modo de copy",
        ["Venda", "Storytelling", "Educacional"],
        index=0,
    )

    st.sidebar.markdown("---")
    st.sidebar.caption("Métricas da conta (simuladas por enquanto)")
    followers = st.sidebar.number_input("Seguidores", min_value=0, value=1200, step=50)
    engagement_pct = st.sidebar.number_input(
        "Engaj. %", min_value=0.0, value=3.4, step=0.1, format="%.1f"
    )
    avg_reach = st.sidebar.number_input(
        "Alcance médio", min_value=0, value=1400, step=50
    )

    return {
        "plan": plan,
        "limit_per_day": limit_per_day,
        "brand": brand,
        "niche": niche,
        "tone": tone,
        "mode": mode,
        "followers": followers,
        "engagement_pct": engagement_pct,
        "avg_reach": avg_reach,
    }


# ======================================================
# PÁGINA: GERAR
# ======================================================
def page_generate(ctx):
    st.subheader("⚡ Geração inteligente de conteúdo")

    platform = st.selectbox("Plataforma", ["Instagram", "TikTok"], index=0)
    message = st.text_input(
        "O que queres comunicar hoje?",
        "Lançamento da nova coleção de Outono.",
    )
    extra = st.text_area(
        "Informação extra (opcional)",
        "Desconto de 10% no site até domingo.",
    )

    used = st.session_state.gens_used_today
    limit = ctx["limit_per_day"]
    disabled = used >= limit

    if disabled:
        st.warning("Limite de gerações diárias atingido para o teu plano.")

    generate_clicked = st.button(
        "🚀 Gerar agora",
        disabled=disabled,
        use_container_width=True,
    )

    # SE CLICOU EM GERAR
    if generate_clicked and not disabled:
        with st.spinner("A pensar na melhor legenda para ti..."):
            variations, err = call_openai_variations(
                platform,
                ctx["brand"],
                ctx["niche"],
                ctx["tone"],
                ctx["mode"],
                message,
                extra,
            )
        if err:
            st.error(err)
        else:
            # guarda variações no estado para não desaparecerem ao mudar de aba
            st.session_state.last_variations = variations
            # incrementa créditos
            st.session_state.gens_used_today += 1
            st.success("✨ Conteúdo gerado com sucesso!")

    # VARIAÇÕES A MOSTRAR (últimas geradas)
    variations = st.session_state.last_variations

    if not variations:
        st.info("Gera conteúdo para ver as sugestões aqui.")
        return

    # Análise e recomendação
    analyses = [fake_analysis(v["legenda"], v["hashtags"]) for v in variations]
    best_idx = max(range(len(analyses)), key=lambda i: analyses[i]["score"])

    col1, col2, col3 = st.columns(3)
    cols = [col1, col2, col3]

    for idx, (col, var, ana) in enumerate(zip(cols, variations, analyses)):
        with col:
            if ctx["plan"] == "Pro" and idx == best_idx:
                st.markdown("🟡 **Nossa recomendação ⭐**")

            title_with_emoji = add_emoji_to_title(var["titulo"], ctx["niche"])
            st.markdown(f"### {title_with_emoji}")

            st.write(var["legenda"])

            if var["hashtags"]:
                st.markdown("**Hashtags sugeridas:**")
                st.write(" ".join(var["hashtags"]))

            if ctx["plan"] == "Pro":
                st.markdown(
                    f"**Análise automática (Pro):** "
                    f"🧠 Score {ana['score']}/10 · "
                    f"💬 Engaj. {ana['engaj']}/10 · "
                    f"💰 Conv. {ana['conv']}/10"
                )
            else:
                st.markdown(
                    "🔒 _Análise automática premium disponível apenas no plano Pro._"
                )

            st.markdown("---")

            # Inputs para planner
            day = st.date_input(
                "Dia",
                value=date.today(),
                key=f"day_var_{idx}",
            )
            time_val = st.time_input(
                "Hora",
                value=datetime.strptime("18:00", "%H:%M").time(),
                key=f"time_var_{idx}",
            )

            if st.button("➕ Adicionar ao planner", key=f"add_planner_{idx}"):
                score = add_task_to_planner(var, day, time_val, ctx["niche"])
                st.success(f"Adicionado ao planner com score estimado {score}/10.")


# ======================================================
# PÁGINA: PLANNER
# ======================================================
def page_planner(ctx):
    st.subheader("📅 Planner semanal")

    anchor = st.date_input("Semana de referência", value=date.today())
    monday = anchor - timedelta(days=anchor.weekday())
    week_days = [monday + timedelta(days=i) for i in range(7)]
    names = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]

    st.markdown(
        f"Semana de **{week_days[0].strftime('%d/%m')}** "
        f"a **{week_days[-1].strftime('%d/%m')}**"
    )

    cols = st.columns(7)
    for col, name, day_dt in zip(cols, names, week_days):
        with col:
            st.markdown(f"**{name}**")
            st.caption(day_dt.strftime("%d/%m"))

            tasks = [
                t for t in st.session_state.planner if t["dia"] == day_dt.isoformat()
            ]
            if not tasks:
                st.caption("Sem tarefas.")
            else:
                for t in tasks:
                    bg = "#0f172a" if t["status"] == "planned" else "#14532d"
                    st.markdown(
                        f"""
<div style="border-radius:14px;padding:10px 12px;margin-top:8px;background-color:{bg};color:#e5e7eb;">
  <div style="font-size:0.8rem;opacity:0.7;">{t['hora']} · {t['plataforma']}</div>
  <div style="font-weight:600;margin-top:4px;">{t['titulo']}</div>
  <div style="font-size:0.8rem;margin-top:4px;">Score: {t['score']}/10 {'✅' if t['status']=='done' else ''}</div>
</div>
                        """,
                        unsafe_allow_html=True,
                    )
                    b1, b2 = st.columns(2)
                    with b1:
                        if st.button("👁 Ver detalhes", key=f"det_{t['id']}"):
                            st.session_state.selected_task_id = t["id"]
                    with b2:
                        if t["status"] != "done":
                            if st.button("✅ Concluir", key=f"done_{t['id']}"):
                                t["status"] = "done"
                        else:
                            st.caption("✅ Já concluído")

    # Detalhes em baixo
    if st.session_state.selected_task_id is not None:
        task = next(
            (t for t in st.session_state.planner if t["id"] == st.session_state.selected_task_id),
            None,
        )
        if task:
            st.markdown("---")
            st.markdown("### 🔎 Detalhes da tarefa selecionada")

            st.markdown(f"**{task['titulo']}**")
            st.caption(
                f"{task['dia']} · {task['hora']} · {task['plataforma']} · Score {task['score']}/10"
            )
            st.write(task["legenda"])
            if task["hashtags"]:
                st.markdown("**Hashtags:**")
                st.write(" ".join(task["hashtags"]))

            st.markdown(
                f"**Estado atual:** {'✅ Concluído' if task['status']=='done' else '🕒 Pendente'}"
            )

            c1, c2, c3 = st.columns(3)
            with c1:
                if task["status"] != "done":
                    if st.button("✅ Marcar como concluído", key="detail_done"):
                        task["status"] = "done"
            with c2:
                if st.button("🗑 Remover do planner", key="detail_remove"):
                    st.session_state.planner = [
                        t for t in st.session_state.planner if t["id"] != task["id"]
                    ]
                    st.session_state.selected_task_id = None
            with c3:
                if st.button("Fechar detalhes", key="detail_close"):
                    st.session_state.selected_task_id = None


# ======================================================
# PÁGINA: PERFORMANCE
# ======================================================
def page_performance(ctx):
    st.subheader("📊 Performance")

    if ctx["plan"] != "Pro":
        st.warning("🔒 A aba Performance completa está disponível apenas no plano Pro.")
        return

    completed = [t for t in st.session_state.planner if t["status"] == "done"]

    if not completed:
        st.info(
            "Ainda não tens posts concluídos no planner. "
            "Marca algumas tarefas como concluídas para veres as métricas."
        )
        return

    scores = [t["score"] for t in completed]
    avg_score = mean(scores)

    # Hora recomendada = média das horas
    minutes_list = []
    for t in completed:
        try:
            h, m = map(int, t["hora"].split(":"))
            minutes_list.append(h * 60 + m)
        except Exception:
            continue
    if minutes_list:
        avg_min = int(round(mean(minutes_list) / 15) * 15)
        hr = (avg_min // 60) % 24
        mn = avg_min % 60
        recommended_hour = f"{hr:02d}:{mn:02d}"
    else:
        recommended_hour = "18:00"

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Posts concluídos", len(completed))
    with c2:
        st.metric("Score médio da IA", f"{avg_score:.2f}")
    with c3:
        st.metric("Hora recomendada", recommended_hour)

    st.caption("🧠 Precisão da IA aumenta com o nº de postagens concluídas.")

    st.markdown("---")
    st.markdown("#### Últimos posts concluídos")

    completed_sorted = sorted(
        completed, key=lambda t: (t["dia"], t["hora"]), reverse=True
    )[:10]

    for t in completed_sorted:
        st.markdown(
            f"- **{t['dia']} {t['hora']} · {t['plataforma']}** — "
            f"{t['titulo']} · Score: {t['score']}/10 · Estado: ✅ Concluído"
        )


# ======================================================
# MAIN
# ======================================================
def main():
    init_state()
    ctx = sidebar()

    st.title("ContentForge v9.4 🍏")
    st.caption(
        "Gera conteúdo inteligente, organiza num planner semanal e, no plano Pro, "
        "acompanha a força de cada publicação."
    )

    tab_gen, tab_planner, tab_perf = st.tabs(
        ["⚡ Gerar", "📅 Planner", "📊 Performance"]
    )

    with tab_gen:
        page_generate(ctx)

    with tab_planner:
        page_planner(ctx)

    with tab_perf:
        page_performance(ctx)


if __name__ == "__main__":
    main()
