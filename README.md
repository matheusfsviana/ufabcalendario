# 📅 Gerador de Calendário UFABC

Ferramenta simples para converter o "Resumo de Matrícula" da UFABC em um arquivo de agenda (`.ics`) compatível com Google Calendar, Outlook e Apple Calendar.

## 🚀 Como usar

Acesse a versão online (não requer instalação):
**[🔗 Clique aqui para abrir a ferramenta](COLOCAR_SEU_LINK_DO_STREAMLIT_AQUI)**

1. Cole o texto do seu resumo de matrícula.
2. O sistema cruza os dados com o PDF oficial de turmas.
3. Baixe o arquivo `.ics` e importe na sua agenda.

## 🛠️ Tecnologias

- **Python** (Lógica de processamento)
- **Streamlit** (Interface Web)
- **Pandas & PDFPlumber** (ETL de dados do PDF)
- **ICS** (Geração do protocolo iCalendar com regras de recorrência)

## 📦 Como rodar localmente (Devs)

1. Clone o repositório:
   ```bash
   git clone [https://github.com/SEU_USUARIO/ufabc-calendario.git](https://github.com/SEU_USUARIO/ufabc-calendario.git)
