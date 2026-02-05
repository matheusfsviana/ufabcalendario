import streamlit as st
import pdfplumber
import pandas as pd
import re
import os
from ics import Calendar, Event
from ics.grammar.parse import ContentLine
from datetime import datetime, timedelta, time
import pytz

# ==========================================
# 🔧 CONFIGURAÇÕES DO QUADRIMESTRE (EDITE AQUI ANUALMENTE)
# ==========================================
# Nome exato do arquivo PDF que deve estar na mesma pasta deste script no GitHub
ARQUIVO_PDF_PADRAO = "turmas_salas_docentes_2026_1.pdf"

# Datas de início e fim das aulas (Ano, Mês, Dia)
DATA_INICIO_AULAS = datetime(2026, 2, 2)
DATA_FIM_AULAS = datetime(2026, 4, 25)
# ==========================================

st.set_page_config(page_title="Calendário UFABC - Comunidade", layout="centered")

# Timezones
TZ_BR = pytz.timezone("America/Sao_Paulo")
TZ_UTC = pytz.utc

def extract_data_from_pdf(pdf_file):
    """Extrai dados do PDF (aceita caminho do arquivo ou objeto de upload)."""
    all_rows = []
    # Se for string (caminho local), abre. Se for objeto (upload), usa direto.
    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            table = page.extract_table()
            if table:
                for row in table:
                    if row and row[0] != 'CURSO': 
                        all_rows.append(row)
    
    df = pd.DataFrame(all_rows)
    if len(df.columns) >= 10:
        df = df.iloc[:, :10]
        df.columns = ['CURSO', 'CODIGO', 'TURMA', 'TEORIA', 'PRATICA', 
                      'DOC_TEORIA_1', 'DOC_TEORIA_2', 'DOC_TEORIA_3', 
                      'DOC_PRATICA_1', 'DOC_PRATICA_2']
    return df

def parse_enrollment_text(text):
    """Lê o resumo de matrícula."""
    disciplines = []
    raw_blocks = re.split(r'(?m)^([A-Z]{4}\d{3}-\d{2}.*)', text)
    current_disc = None
    
    for block in raw_blocks:
        if not block.strip(): continue
        header_match = re.match(r'([A-Z]{4}\d{3}-\d{2}) - (.*?) \((.*?)\) -', block)
        
        if header_match:
            if current_disc: disciplines.append(current_disc)
            full_name_turma = header_match.group(2).strip()
            turma_match = re.search(r'([A-Z]\d+-(Noturno|Matutino))$', full_name_turma)
            turma = turma_match.group(1) if turma_match else ""
            name_only = full_name_turma.replace(turma, "").strip()
            
            current_disc = {
                'code': header_match.group(1),
                'name': name_only,
                'turma': turma,
                'full_header': full_name_turma,
                'schedules': []
            }
        elif current_disc:
            lines = block.strip().split('\n')
            for line in lines:
                time_match = re.search(r'(Segunda|Terça|Quarta|Quinta|Sexta|Sábado).*?das (\d{2}:\d{2}) às (\d{2}:\d{2}).*?-\s*(.*)', line, re.IGNORECASE)
                if time_match:
                    current_disc['schedules'].append({
                        'day': time_match.group(1).lower(),
                        'start': time_match.group(2),
                        'end': time_match.group(3),
                        'freq': time_match.group(4).strip().lower()
                    })
    if current_disc: disciplines.append(current_disc)
    return disciplines

def find_details_in_pdf(disc, df_pdf):
    """Cruza dados com o DataFrame do PDF."""
    def normalize(s): return re.sub(r'[^a-zA-Z0-9]', '', str(s)).lower()
    search_key = normalize(disc['name'] + disc['turma'])
    
    if df_pdf.empty: return "N/A", ""

    for idx, row in df_pdf.iterrows():
        pdf_turma = normalize(str(row['TURMA']))
        if search_key in pdf_turma:
            teachers = [str(row[c]) for c in ['DOC_TEORIA_1', 'DOC_TEORIA_2', 'DOC_PRATICA_1'] if row[c] and str(row[c]) != 'None']
            teachers = list(set([t for t in teachers if len(t) > 2]))
            raw_loc_str = f"Teoria: {row['TEORIA'] or ''} Prática: {row['PRATICA'] or ''}"
            return ", ".join(teachers), raw_loc_str
    return "Não encontrado", ""

def extract_specific_room(raw_text, day_of_week):
    """Extrai a sala específica do dia."""
    if not raw_text: return "Verificar PDF"
    clean_text = raw_text.replace("\n", " ")
    
    # Busca por dia específico
    pattern = re.compile(rf"{day_of_week}.*?sala\s+([^,]+)", re.IGNORECASE)
    match = pattern.search(clean_text)
    
    candidate = ""
    if match:
        candidate = match.group(1).strip()
    else:
        # Fallback genérico
        match_general = re.search(r'sala\s+([^,]+)', clean_text, re.IGNORECASE)
        if match_general:
            candidate = match_general.group(1).strip() + " (?)"
    
    # Limpeza final
    if candidate:
        candidate = re.sub(r'\s*(semanal|quinzenal).*$', '', candidate, flags=re.IGNORECASE)
        return f"Sala {candidate}"
        
    return "Verificar PDF"

def generate_ics_rrule(disciplines, start_date, end_date):
    """Gera o calendário."""
    c = Calendar()
    weekdays = {'segunda': 0, 'terça': 1, 'quarta': 2, 'quinta': 3, 'sexta': 4, 'sábado': 5, 'domingo': 6}
    
    # Converter para datetime completo se vier apenas date
    if isinstance(start_date, type(datetime.date)):
        start_date = datetime.combine(start_date, time.min)
    if isinstance(end_date, type(datetime.date)):
        end_date = datetime.combine(end_date, time.max)

    end_date_utc = end_date.replace(hour=23, minute=59, second=59).astimezone(TZ_UTC)
    until_str = end_date_utc.strftime('%Y%m%dT%H%M%SZ')

    for disc in disciplines:
        for sched in disc['schedules']:
            wd_name = sched['day'].split('-')[0]
            wd_num = weekdays.get(wd_name, 0)
            
            days_ahead = wd_num - start_date.weekday()
            if days_ahead < 0: days_ahead += 7
            first_occurrence = start_date + timedelta(days=days_ahead)
            
            interval = 1
            freq_str = "Semanal"
            if 'quinzenal' in sched['freq']:
                interval = 2
                freq_str = "Quinzenal"
                if '(ii)' in sched['freq'] or ' ii' in sched['freq']:
                    first_occurrence += timedelta(days=7)
                    freq_str = "Quinzenal II"
                elif '(i)' in sched['freq'] or ' i' in sched['freq']:
                    freq_str = "Quinzenal I"

            h_start, m_start = map(int, sched['start'].split(':'))
            h_end, m_end = map(int, sched['end'].split(':'))
            
            event_start = first_occurrence.replace(hour=h_start, minute=m_start, tzinfo=TZ_BR)
            event_end = first_occurrence.replace(hour=h_end, minute=m_end, tzinfo=TZ_BR)
            
            clean_room = extract_specific_room(disc.get('room_raw', ''), wd_name)

            e = Event()
            e.name = disc['name']
            e.begin = event_start
            e.end = event_end
            e.location = clean_room
            e.description = f"Prof: {disc.get('professor', 'N/A')}\nFrequência: {freq_str}"
            
            rrule_value = f"FREQ=WEEKLY;INTERVAL={interval};UNTIL={until_str}"
            e.extra.append(ContentLine(name="RRULE", value=rrule_value))
            c.events.add(e)

    return c

# ==========================================
# INTERFACE DO USUÁRIO
# ==========================================

st.title("📅 UFABCalendar - Gerador de Calendário")
st.markdown("""
Cole o texto do seu **Resumo de Matrícula** abaixo para gerar sua agenda automaticamente.
As informações de salas e professores serão cruzadas com a base oficial.
""")

# Lógica de Carregamento do PDF
pdf_source = None
status_msg = st.empty()

# 1. Tenta carregar o PDF padrão da pasta local
if os.path.exists(ARQUIVO_PDF_PADRAO):
    pdf_source = ARQUIVO_PDF_PADRAO
    status_msg.success(f"📚 Base de dados carregada: {ARQUIVO_PDF_PADRAO}")
else:
    # 2. Se não achar (ex: mudou o nome ou não subiu no git), pede upload
    status_msg.warning("⚠️ Arquivo de turmas padrão não encontrado. Por favor, faça o upload.")
    pdf_source = st.file_uploader("Upload PDF Turmas", type="pdf")

# Área de Texto Principal
enrollment_text = st.text_area("Cole aqui seu Resumo de Matrícula:", height=200, placeholder="Ex: ESTA001-17 - DISPOSITIVOS ELETRÔNICOS...")

# Configurações Avançadas (Escondidas por padrão para não confundir)
with st.expander("Verificar Datas do Quadrimestre (Avançado)"):
    st.info("Estas datas já estão configuradas automaticamente. Altere apenas se necessário.")
    col_d1, col_d2 = st.columns(2)
    d_inicio = col_d1.date_input("Início", value=DATA_INICIO_AULAS)
    d_fim = col_d2.date_input("Fim", value=DATA_FIM_AULAS)

if st.button("Gerar Meu Calendário", type="primary", use_container_width=True):
    if pdf_source and enrollment_text:
        with st.spinner("Lendo PDF e gerando eventos..."):
            try:
                # Processamento
                df_pdf = extract_data_from_pdf(pdf_source)
                disciplines = parse_enrollment_text(enrollment_text)
                
                if not disciplines:
                    st.error("Não encontrei nenhuma disciplina no texto colado. Verifique se copiou o resumo inteiro.")
                else:
                    # Cruzamento
                    for disc in disciplines:
                        prof, raw_loc = find_details_in_pdf(disc, df_pdf)
                        disc['professor'] = prof
                        disc['room_raw'] = raw_loc
                    
                    # Geração
                    cal = generate_ics_rrule(disciplines, d_inicio, d_fim)
                    
                    st.success(f"✅ Sucesso! {len(disciplines)} disciplinas encontradas.")
                    
                    # Download
                    st.download_button(
                        label="⬇️ Baixar Agenda (.ics)",
                        data=cal.serialize(),
                        file_name="minhas_aulas_ufabc.ics",
                        mime="text/calendar",
                        type="primary"
                    )
            except Exception as e:
                st.error(f"Ocorreu um erro técnico: {e}")
    else:

        st.warning("Precisamos do texto da matrícula e do PDF carregado para continuar.")

# ==========================================
# RODAPÉ DE CONTATO
# ==========================================
st.divider()  # Linha divisória para separar o app do rodapé

st.markdown("""
<div style="text-align: center;">
    <p>Desenvolvido por <b>Seu Nome</b> | Data Architect & Engineer</p>
    <p>Encontrou um erro ou tem uma sugestão? Entre em contato!</p>
</div>
""", unsafe_allow_html=True)

col1, col2, col3 = st.columns([1, 2, 1])

with col2:
    # Substitua os links abaixo pelos seus reais
    st.link_button("🚀 LinkedIn", "www.linkedin.com/in/mattviana", use_container_width=True)
    st.link_button("💬 Contato WhatsApp", "https://wa.me/5511963598361", use_container_width=True)
