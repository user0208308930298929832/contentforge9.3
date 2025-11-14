import streamlit as st
from datetime import date, time, timedelta
from typing import List, Dict, Any, Optional
from openai import OpenAI
import json
import uuid
import statistics
import re

# -----------------------------
# CONFIG GERAL
# -----------------------------
st.set_page_config(
    page_title="ContentForge v9.3",
    layout="wide",
    page_icon="🍏",
)

st.markdown(
    """
    <style>
    html, body, [class*="css"]  {
        font-family: -apple-system, BlinkMacSystemFont, system-ui, sans-serif;
    }
    .cf-card {
        border-radius: 14px;
        padding: 0.8rem 1rem;
        margin-bottom: 0.5rem;
        background: #111111;
        border: 1px solid #333333;
        color: #f9fafb;
    }
    .cf-card-done {
        background: #0f2913 !important;
        border-color: #16a34a !important;
        color: #dcfce7 !important;
    }
    .cf-badge-reco {
        display: inline-flex;
        align-items: center;
        padding: 0.15rem 0.6rem;
        border-radius: 999px;
        background: #f7e49c;
        color: #3a2c00;
        font-size: 0.8rem;
        font-weight: 600;
        margin-bottom: 0.4rem;
    }
    .cf-badge-lock {
        display:inline-flex;
        align-items:center;
        padding:0.4rem 0.8rem;
        border-radius:999px;
        background:#3f3f46;
        color:#e4e4e7;
        font-size:0.85rem;
        margin-top:0.3rem;
    }
    .cf-subtle {
        font-size: 0.8rem;
        opacity: 0.7;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# -----------------------------
# CLIENTE OPENAI (SDK NOVA)
# -----------------------------
@st.cache_resource
def get_openai_client() -> OpenAI:
    return OpenAI(api_key=st.secrets["OPENAI_API_KEY"])


# -----------------------------
# ESTADO INICIAL
# -----------------------------
if "planner_items" not in st.session_state:
    st.session_state.planner_items: List[Dict[str, Any]] = []

if "anchor_date" not in st.session_state:
    st.session_state.anchor_date: date = date.today()

if "selected_task_id" not in st.session_state:
    st.session_state.selected_task_id: Optional[str] = None

if "geracoes_hoje" not in st.session_state:
    st.session_state.geracoes_hoje: int = 0

if "data_creditos" not in st.session_state:
    st.session_state.data_creditos: date = date.today()

if "ultimas_variacoes" not in st.session_state:
    st.session_state.ultimas_variacoes: List[Dict[str, Any]] = []

if "added_variations" not in st.session_state:
    st.session_state.added_variations: set[str] = set()


# -----------------------------
# RESET DIÁRIO DOS CRÉDITOS
# -----------------------------
if st.session_state.data_creditos != date.today():
    st.session_state.geracoes_hoje = 0
    st.session_state.data_creditos = date.today()


# -----------------------------
# FUNÇÕES AUXILIARES
# -----------------------------
def analise_automatica_legenda(texto: str) -> Dict[str, float]:
    """
    Heurística local para análise automática (sem nova chamada à API).
    """
    length = len(texto)
    clareza = 7.0
    if length < 140:
        clareza += 1
    if "?" in texto:
        clareza += 0.5

    eng = 6.0
    emojis = sum(ch in "🔥✨💥🎯💡🧠❤️😍📣📌💬😊😉🤩" for ch in texto)
    if emojis >= 2:
        eng += 1
    if any(word in texto.lower() for word in ["comenta", "partilha", "guarda", "marca alguém", "marca alguem"]):
        eng += 1

    conv = 6.0
    if any(x in texto.lower() for x in ["link na bio", "site", "loja", "desconto", "%", "cupão", "cupom"]):
        conv += 1
    if any(x in texto.lower() for x in ["até hoje", "até domingo", "hoje apenas", "limitado", "últimas unidades"]):
        conv += 1

    clareza = max(0.0, min(10.0, clareza))
    eng = max(0.0, min(10.0, eng))
    conv = max(0.0, min(10.0, conv))
    score = round((clareza + eng + conv) / 3, 1)

    return {
        "clareza": round(clareza, 1),
        "engajamento": round(eng, 1),
        "conversao": round(conv, 1),
        "score_final": score,
    }


def parse_variacoes_texto(raw: str) -> List[Dict[str, Any]]:
    """
    Fallback se o modelo não devolver JSON.
    Procura blocos 'IDEIA 1:', 'IDEIA 2:'...
    """
    partes = re.split(r"IDEIA\s+\d+\s*:", raw, flags=re.IGNORECASE)
    # primeira parte é lixo antes da IDEA 1
    partes = [p.strip() for p in partes[1:] if p.strip()]
    variacoes = []
    for p in partes:
        linhas = [l.strip() for l in p.splitlines() if l.strip()]
        legenda = "\n".join([l for l in linhas if not l.lower().startswith("hashtags") and not l.startswith("#")])
        # hashtags: linhas que começam por #
        hashtags = []
        for l in linhas:
            if l.startswith("#"):
                tokens = l.replace(",", " ").split()
                for t in tokens:
                    if t.startswith("#"):
                        hashtags.append(t)
        titulo = (linhas[0] if linhas else "Ideia")[:60]
        variacoes.append(
            {
                "titulo_planner": titulo,
                "legenda": legenda,
                "hashtags": hashtags,
                "score_final": 0,
                "engajamento": 0,
                "conversao": 0,
                "recomendado": False,
            }
        )
    return variacoes


def gerar_variacoes_legenda(
    marca: str,
    nicho: str,
    tom: str,
    modo_copy: str,
    plataforma: str,
    mensagem: str,
    extra: Optional[str],
    plano: str,
) -> List[Dict[str, Any]]:
    """
    Pede 3 variações ao modelo. Tenta JSON, senão faz fallback por texto.
    """
    system_prompt = (
        "És o ContentForge, um assistente de marketing que cria legendas premium "
        "em PT-PT para Instagram e TikTok. "
        "Estilo moderno, emocional quando faz sentido, mas profissional. "
        "Usa ENTRE 2 e 4 emojis por legenda, bem colocados, nunca spam. "
        "Mantém frases curtas, diretas e fáceis de ler no telemóvel."
    )

    user_prompt = f"""
Marca: {marca}
Nicho: {nicho}
Plataforma: {plataforma}
Tom de voz: {tom}
Modo de copy: {modo_copy}
Mensagem principal: {mensagem}
Informação extra: {extra or "sem informação extra"}

TAREFA:
Cria EXACTAMENTE 3 variações de legenda para um post em {plataforma}.

Cada variação deve ter:
- Gancho forte na primeira frase
- Corpo com storytelling curto OU venda clara
- CTA sólido
- 2 a 4 emojis relevantes
- Hashtags em baixo

FORMATO DA RESPOSTA (OBRIGATÓRIO):

[
  {{
    "titulo_planner": "...",
    "legenda": "...",
    "hashtags": ["#tag1", "#tag2", "..."],
    "score_final": 0-10,
    "engajamento": 0-10,
    "conversao": 0-10,
    "recomendado": true/false
  }},
  ...
]

Responde apenas com JSON válido.
"""

    client = get_openai_client()
    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.85,
    )

    raw = response.choices[0].message.content.strip()

    # Tentar JSON
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            data = [data]
        # normalizar
        variacoes: List[Dict[str, Any]] = []
        for v in data:
            variacoes.append(
                {
                    "titulo_planner": v.get("titulo_planner") or "Ideia",
                    "legenda": v.get("legenda") or "",
                    "hashtags": v.get("hashtags") or [],
                    "score_final": float(v.get("score_final", 0) or 0),
                    "engajamento": float(v.get("engajamento", 0) or 0),
                    "conversao": float(v.get("conversao", 0) or 0),
                    "recomendado": bool(v.get("recomendado", False)),
                }
            )
        return variacoes
    except Exception:
        # fallback: parse texto
        return parse_variacoes_texto(raw)


def add_to_planner(
    dia: date,
    hora: time,
    plataforma: str,
    titulo: str,
    legenda: str,
    hashtags: List[str],
    score: float,
) -> None:
    item: Dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "date": dia,
        "time": hora,
        "plataforma": plataforma,
        "titulo": titulo,
        "legenda": legenda,
        "hashtags": hashtags,
        "score": score,
        "status": "planned",
    }
    st.session_state.planner_items.append(item)


def get_week_range(anchor: date) -> List[date]:
    weekday = anchor.weekday()  # 0 = Monday
    monday = anchor - timedelta(days=weekday)
    return [monday + timedelta(days=i) for i in range(7)]


def get_selected_task() -> Optional[Dict[str, Any]]:
    tid = st.session_state.selected_task_id
    if not tid:
        return None
    for item in st.session_state.planner_items:
        if item["id"] == tid:
            return item
    return None


# -----------------------------
# SIDEBAR – PLANO E PERFIL
# -----------------------------
st.sidebar.title("Plano e perfil")

plano = st.sidebar.selectbox("Plano", ["Starter", "Pro"], index=0)

limite_hoje = 5 if plano == "Starter" else 9999
st.sidebar.write(
    f"🔋 Gerações usadas hoje: **{st.session_state.geracoes_hoje}/{limite_hoje}**"
)

st.sidebar.markdown("---")

marca = st.sidebar.text_input("Marca", value="Loukisses")
nicho = st.sidebar.text_input("Nicho/tema", value="Moda feminina")
tom = st.sidebar.selectbox("Tom de voz", ["premium", "casual", "profissional", "emocional"], index=0)
modo_copy = st.sidebar.selectbox("Modo de copy", ["Venda", "Storytelling", "Educacional"], index=0)

st.sidebar.markdown("---")
st.sidebar.markdown("**Métricas da conta (simuladas)**")
seguidores = st.sidebar.number_input("Seguidores", min_value=0, value=1200, step=50)
eng_percent = st.sidebar.number_input("Engaj. %", min_value=0.0, max_value=100.0, value=3.4, step=0.1)
alcance_medio = st.sidebar.number_input("Alcance médio", min_value=0, value=1400, step=50)
st.sidebar.markdown(
    '<span class="cf-subtle">Integração real por link fica para o plano Pro+ numa futura versão.</span>',
    unsafe_allow_html=True,
)

# -----------------------------
# HEADER
# -----------------------------
st.markdown("## ContentForge v9.3 🍏")
st.markdown(
    "Gera conteúdo inteligente, organiza num planner semanal e, no plano **Pro**, "
    "acompanha a força de cada publicação."
)

tabs = st.tabs(["⚡ Gerar", "📅 Planner", "📊 Performance"])


# -----------------------------
# ABA 1 – GERAR
# -----------------------------
with tabs[0]:
    st.markdown("### ⚡ Geração inteligente de conteúdo")

    col_top1, _ = st.columns([2, 1])
    with col_top1:
        plataforma = st.selectbox("Plataforma", ["Instagram", "TikTok"], index=0)

    mensagem = st.text_input(
        "O que queres comunicar hoje?",
        value="Apresentação da nova coleção de Outono",
    )
    extra = st.text_area(
        "Informação extra (opcional)",
        value="10% de desconto no site até domingo.",
        height=80,
    )

    if plano == "Starter":
        st.markdown(
            """
            <div class="cf-subtle">
            🔒 <b>Dica Pro:</b> No plano Pro calculamos automaticamente a qualidade do copy,
            a probabilidade de engajamento e conversão para cada variação.
            </div>
            """,
            unsafe_allow_html=True,
        )

    gerar = st.button("⚡ Gerar agora", type="primary")

    if gerar:
        if st.session_state.geracoes_hoje >= limite_hoje:
            st.error(f"Limite diário de {limite_hoje} gerações atingido no plano {plano}.")
        else:
            with st.spinner("A IA está a pensar na melhor legenda para ti..."):
                variacoes = gerar_variacoes_legenda(
                    marca=marca,
                    nicho=nicho,
                    tom=tom,
                    modo_copy=modo_copy,
                    plataforma=plataforma,
                    mensagem=mensagem,
                    extra=extra,
                    plano=plano,
                )

            if not variacoes:
                st.error("Não consegui interpretar a resposta da API. Tenta novamente.")
            else:
                st.session_state.geracoes_hoje += 1
                st.session_state.ultimas_variacoes = variacoes
                st.session_state.added_variations = set()
                st.success("✨ Conteúdo gerado com sucesso!")

    variacoes_to_show = st.session_state.ultimas_variacoes

    if variacoes_to_show:
        # escolher melhor para badge
        best_idx = 0
        best_score = -1.0
        for i, v in enumerate(variacoes_to_show):
            score = float(v.get("score_final", 0) or 0)
            if v.get("recomendado") or score > best_score:
                best_score = score
                best_idx = i

        st.markdown("### Resultados")

        cols = st.columns(3)
        for idx, (col, var) in enumerate(zip(cols, variacoes_to_show)):
            with col:
                titulo = var.get("titulo_planner") or f"Ideia {idx+1}"
                legenda = var.get("legenda") or ""
                hashtags_raw = var.get("hashtags") or []
                hashtags = [h if h.startswith("#") else f"#{h.strip()}" for h in hashtags_raw]

                # análise automática local
                analise = analise_automatica_legenda(legenda)
                score_api = float(var.get("score_final", 0) or 0)
                final_score = round((score_api + analise["score_final"]) / 2, 1) if score_api else analise["score_final"]

                # badge de recomendação só no Pro
                if plano == "Pro" and idx == best_idx:
                    st.markdown(
                        '<div class="cf-badge-reco">⭐ Nossa recomendação</div>',
                        unsafe_allow_html=True,
                    )

                st.markdown(f"**{titulo}**")
                st.write(legenda)

                if hashtags:
                    st.markdown("**Hashtags sugeridas:**")
                    st.write(" ".join(hashtags))

                if plano == "Pro":
                    st.markdown(
                        f"**Análise automática:** "
                        f"🧠 Score {final_score}/10 · "
                        f"💬 Engaj. {analise['engajamento']}/10 · "
                        f"💰 Conv. {analise['conversao']}/10"
                    )
                else:
                    st.markdown(
                        f"**Análise automática (Pro):** 🔒 Pré-visualização — "
                        f"score estimado ~{final_score}/10"
                    )

                dia = st.date_input(
                    "Dia",
                    value=date.today(),
                    key=f"dia_{idx}",
                )
                hora = st.time_input(
                    "Hora",
                    value=time(18, 0),
                    key=f"hora_{idx}",
                )

                # chave única da variação para não duplicar no planner
                variation_key = f"{titulo}_{hash(legenda) % 10_000_000}"

                if variation_key in st.session_state.added_variations:
                    st.button("✔ Adicionado ao planner", disabled=True, key=f"add_{idx}")
                else:
                    if st.button("➕ Adicionar ao planner", key=f"add_{idx}"):
                        add_to_planner(
                            dia=dia,
                            hora=hora,
                            plataforma=plataforma.lower(),
                            titulo=titulo,
                            legenda=legenda,
                            hashtags=hashtags,
                            score=final_score,
                        )
                        st.session_state.added_variations.add(variation_key)
                        st.success("Adicionado ao planner ✅")


# -----------------------------
# ABA 2 – PLANNER
# -----------------------------
with tabs[1]:
    st.markdown("### 📅 Planner de Conteúdo (v9.3)")
    st.markdown("_Vista semanal clean, com tarefas planeadas e concluídas._")

    col_nav1, col_nav2, col_anchor = st.columns([1, 1, 2])
    with col_nav1:
        if st.button("« Semana anterior"):
            st.session_state.anchor_date -= timedelta(days=7)
    with col_nav2:
        if st.button("Semana seguinte »"):
            st.session_state.anchor_date += timedelta(days=7)
    with col_anchor:
        new_anchor = st.date_input("Semana de referência", value=st.session_state.anchor_date)
        st.session_state.anchor_date = new_anchor

    semana = get_week_range(st.session_state.anchor_date)
    semana_label = f"Semana de {semana[0].strftime('%d/%m')} a {semana[-1].strftime('%d/%m')}"
    st.markdown(f"**{semana_label}**")

    cols_dias = st.columns(7)
    nomes_dias = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]

    for col_dia, nome, dia in zip(cols_dias, nomes_dias, semana):
        with col_dia:
            st.markdown(f"**{nome}**")
            st.caption(dia.strftime("%d/%m"))

            items_dia = sorted(
                [it for it in st.session_state.planner_items if it["date"] == dia],
                key=lambda x: x["time"],
            )

            if not items_dia:
                st.write('<span class="cf-subtle">Sem tarefas.</span>', unsafe_allow_html=True)
            else:
                for item in items_dia:
                    status = item["status"]
                    card_classes = "cf-card cf-card-done" if status == "done" else "cf-card"
                    html = f"""
                    <div class="{card_classes}">
                        <div style="font-size:0.8rem; opacity:0.75;">
                            {item['time'].strftime('%H:%M')} · {item['plataforma'].capitalize()}
                        </div>
                        <div style="font-weight:600; margin-top:0.15rem;">
                            {item['titulo']}
                        </div>
                        <div style="font-size:0.8rem; margin-top:0.2rem;">
                            Score: {item['score']}/10
                            {' · ✅ Concluído' if status == 'done' else ''}
                        </div>
                    </div>
                    """
                    st.markdown(html, unsafe_allow_html=True)

                    col_bt1, col_bt2 = st.columns(2)
                    with col_bt1:
                        if st.button("👁 Ver detalhes", key=f"det_{item['id']}"):
                            st.session_state.selected_task_id = item["id"]
                    with col_bt2:
                        if status == "planned":
                            if st.button("✅ Concluir", key=f"done_{item['id']}"):
                                item["status"] = "done"
                                st.success("Marcado como concluído ✅")
                        else:
                            st.write('<span class="cf-subtle">Já concluído</span>', unsafe_allow_html=True)

    st.markdown("---")
    sel = get_selected_task()
    if sel:
        st.markdown("### 🔍 Detalhes da tarefa selecionada")
        colA, colB = st.columns([2, 1])
        with colA:
            st.markdown(f"**{sel['titulo']}**")
            st.caption(
                f"{sel['date'].strftime('%d/%m/%Y')} · {sel['time'].strftime('%H:%M')} · "
                f"{sel['plataforma'].capitalize()}"
            )
            st.write(sel["legenda"])

            if sel["hashtags"]:
                st.markdown("**Hashtags:**")
                st.write(" ".join(sel["hashtags"]))

        with colB:
            st.markdown("**Estado atual:**")
            if sel["status"] == "done":
                st.success("Concluído ✅")
            else:
                st.info("Planeado")

            if sel["status"] == "planned":
                if st.button("✅ Marcar como concluído", key="det_mark_done"):
                    sel["status"] = "done"
                    st.success("Marcado como concluído ✅")
            else:
                st.write('<span class="cf-subtle">Já está concluído.</span>', unsafe_allow_html=True)

            if st.button("🗑 Remover do planner", key="det_remove"):
                st.session_state.planner_items = [
                    it for it in st.session_state.planner_items if it["id"] != sel["id"]
                ]
                st.session_state.selected_task_id = None
                st.success("Tarefa removida.")

        if st.button("Fechar detalhes"):
            st.session_state.selected_task_id = None


# -----------------------------
# ABA 3 – PERFORMANCE PREMIUM (v10)
# -----------------------------
with tabs[2]:
    st.markdown("### 📊 Performance Pro – Analytics Inteligentes")

    if plano != "Pro":
        st.markdown(
            """
            <div class="cf-badge-lock">
            🔒 Disponível no plano Pro. Desbloqueia métricas avançadas, previsões e insights inteligentes.
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.info("Altera o plano na barra lateral para 'Pro' para aceder ao dashboard completo de performance.")
    else:
        concluidos = [it for it in st.session_state.planner_items if it["status"] == "done"]
        planeados_total = len(st.session_state.planner_items)

        if not concluidos:
            st.info("Ainda não tens posts marcados como concluídos. Marca pelo menos 1 tarefa como concluída no Planner para começar a ver analytics.")
        else:
            # ---------------- KPI CARDS ----------------
            scores = [float(it["score"]) for it in concluidos if isinstance(it.get("score"), (int, float, str))]
            scores = [float(s) for s in scores]
            media_score = round(statistics.mean(scores), 2) if scores else 0.0

            # consistência: concluídos / planeados
            consistencia = 0.0
            if planeados_total > 0:
                consistencia = round((len(concluidos) / planeados_total) * 100, 1)

            # hora recomendada (mais frequente entre as concluídas)
            horas = [it["time"].strftime("%H:00") for it in concluidos]
            if horas:
                hora_recomendada = max(set(horas), key=horas.count)
            else:
                hora_recomendada = "18:00"

            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Score médio da IA", f"{media_score}/10")
                st.caption("Média das últimas publicações concluídas.")
            with col2:
                st.metric("Consistência semanal", f"{consistencia}%")
                st.caption("Posts concluídos vs. planeados.")
            with col3:
                st.metric("Hora recomendada", hora_recomendada)
                st.caption("Baseado nos teus posts concluídos.")

            st.markdown(
                '<div class="cf-subtle">🧠 A precisão destas métricas aumenta com o número de postagens concluídas.</div>',
                unsafe_allow_html=True,
            )

            st.markdown("---")

            # ---------------- GRÁFICO – EVOLUÇÃO DA FORÇA ----------------
            st.markdown("#### 📈 Evolução da força das tuas publicações")

            concluidos_sorted = sorted(
                concluidos,
                key=lambda x: (x["date"], x["time"]),
            )

            chart_scores = [it["score"] for it in concluidos_sorted]
            chart_labels = [it["date"].strftime("%d/%m") for it in concluidos_sorted]

            # streamlit aceita listas simples; eixo X será o índice (1,2,3...)
            st.line_chart(chart_scores)
            st.caption("Cada ponto representa o score de uma publicação concluída, ao longo do tempo.")

            st.markdown("---")

            # ---------------- INSIGHTS INTELIGENTES ----------------
            st.markdown("#### ✨ Insights inteligentes da IA")

            # melhor e pior post por score
            best_post = max(concluidos, key=lambda x: x["score"])
            worst_post = min(concluidos, key=lambda x: x["score"])

            # plataforma com melhor performance
            plataformas = {}
            for it in concluidos:
                plataformas.setdefault(it["plataforma"], []).append(it["score"])
            melhor_plat = None
            melhor_plat_score = 0.0
            for plat, vals in plataformas.items():
                m = statistics.mean(vals)
                if m > melhor_plat_score:
                    melhor_plat_score = m
                    melhor_plat = plat

            col_ins1, col_ins2 = st.columns(2)
            with col_ins1:
                st.markdown("**🔥 Insight #1 – Tipo de conteúdo forte**")
                st.write(
                    f"O teu melhor post foi em **{best_post['plataforma'].capitalize()}** "
                    f"a {best_post['date'].strftime('%d/%m')} às {best_post['time'].strftime('%H:%M')} "
                    f"com score **{best_post['score']}/10**."
                )
                st.write("A estrutura deste post é uma boa referência para novos conteúdos.")

                st.markdown("**📉 Insight #2 – O que evitar**")
                st.write(
                    f"O post com menor score foi em **{worst_post['plataforma'].capitalize()}** "
                    f"a {worst_post['date'].strftime('%d/%m')} às {worst_post['time'].strftime('%H:%M')} "
                    f"com score **{worst_post['score']}/10**."
                )
                st.write("Evita repetir o mesmo tipo de abordagem sem ajustares o copy ou o hook inicial.")

            with col_ins2:
                st.markdown("**📢 Insight #3 – Plataforma em alta**")
                if melhor_plat:
                    st.write(
                        f"A plataforma com melhor performance média é **{melhor_plat.capitalize()}** "
                        f"com score médio aproximado de **{round(melhor_plat_score, 1)}/10**."
                    )
                else:
                    st.write("Ainda não há dados suficientes para comparar plataformas.")

                st.markdown("**⏱ Insight #4 – Janela horária forte**")
                if horas:
                    st.write(
                        f"A maior concentração de posts concluídos está por volta das **{hora_recomendada}**. "
                        "Tens boas probabilidades de manter esta hora como base para próximos conteúdos."
                    )
                else:
                    st.write("Assim que tiveres mais posts concluídos, sugerimos uma hora mais precisa para publicar.")

            st.markdown("---")

            # ---------------- PREVISÃO PRO – O QUE POSTAR A SEGUIR ----------------
            st.markdown("#### 🔮 Previsão Pro – O que postar a seguir")

            sugestao_tema = "benefício direto + prova social"
            if melhor_plat == "instagram":
                sugestao_tema = "carrossel educativo com foco em valor e CTA para o link na bio"
            elif melhor_plat == "tiktok":
                sugestao_tema = "vídeo curto com hook forte nos primeiros 3 segundos e CTA para seguir a página"

            st.write(
                f"Com base nos posts que já concluíste, a IA sugere que o teu próximo conteúdo seja em "
                f"**{(melhor_plat or 'Instagram').capitalize()}**, publicado por volta das **{hora_recomendada}**, "
                f"com foco em **{sugestao_tema}**."
            )
            st.caption("Esta previsão é aproximada e melhora à medida que completas mais tarefas no planner.")

            st.markdown("---")

            # ---------------- ÚLTIMOS POSTS CONCLUÍDOS ----------------
            st.markdown("#### 🧾 Últimos posts concluídos")

            for it in sorted(concluidos, key=lambda x: (x["date"], x["time"]), reverse=True)[:10]:
                st.markdown(
                    f"**{it['date'].strftime('%d/%m')} {it['time'].strftime('%H:%M')} · "
                    f"{it['plataforma'].capitalize()}** — {it['titulo']}  \n"
                    f"Score: **{it['score']}/10** · Estado: ✅ Concluído"
                )

            st.markdown(
                '<div class="cf-subtle">🧠 A IA está a aprender contigo. Quanto mais publicares e concluires no planner, '
                'mais precisas serão as previsões e insights.</div>',
                unsafe_allow_html=True,
            )
