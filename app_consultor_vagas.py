# ==============================================
# CONSULTOR DE VAGAS UFF - VERSÃO STREAMLIT
# Sistema de consulta de turmas e vagas do Instituto de Química
# Adaptado para funcionar no Streamlit Cloud
# ==============================================

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import io
import zipfile
import re
import requests
import time
import json
from bs4 import BeautifulSoup
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import warnings
warnings.filterwarnings('ignore')

# ===== CONFIGURAÇÃO DA PÁGINA =====
st.set_page_config(
    page_title="Consultor de Vagas UFF - Química",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ===== ESTILOS CSS =====
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1e3a5f;
        text-align: center;
        margin-bottom: 1rem;
    }
    .sub-header {
        font-size: 1.2rem;
        color: #666;
        text-align: center;
        margin-bottom: 0.5rem;
    }
    .developer-name {
        font-weight: bold;
        color: #1e3a5f;
    }
    .metric-card {
        background-color: #f8f9fa;
        border-radius: 0.5rem;
        padding: 1rem;
        border-left: 4px solid #1e3a5f;
        margin-bottom: 1rem;
    }
    .highlight {
        background-color: #fff3cd;
        padding: 0.5rem;
        border-radius: 0.25rem;
        font-weight: bold;
    }
    .success-box {
        background-color: #d4edda;
        border: 1px solid #c3e6cb;
        border-radius: 0.5rem;
        padding: 1rem;
        margin: 1rem 0;
    }
    .warning-box {
        background-color: #fff3cd;
        border: 1px solid #ffeaa7;
        border-radius: 0.5rem;
        padding: 1rem;
        margin: 1rem 0;
    }
</style>
""", unsafe_allow_html=True)

# ===== INICIALIZAR SESSION STATE =====
if 'consultor_dados' not in st.session_state:
    st.session_state.consultor_dados = None
if 'dados_turmas' not in st.session_state:
    st.session_state.dados_turmas = None
if 'processando' not in st.session_state:
    st.session_state.processando = False
if 'resultado_disponivel' not in st.session_state:
    st.session_state.resultado_disponivel = False
if 'periodo_selecionado' not in st.session_state:
    st.session_state.periodo_selecionado = None

# ===== CLASSE DE CONSULTA UFF (Versão Streamlit) =====
class ConsultorQuadroHorariosUFFStreamlit:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'pt-BR,pt;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })
        
        self.base_url = "https://app.uff.br/graduacao/quadrodehorarios/"
        
        # Mapeamento de cursos
        self.ids_cursos = {
            'Química': '28',
            'Química Industrial': '29'
        }
        
        self.cores_cursos = {
            'Química': '#FFE6CC',
            'Química Industrial': '#E6F3FF'
        }
        
        # Cache para requests
        self.cache = {}
    
    def fazer_request(self, url, use_cache=True):
        """Faz uma requisição HTTP com cache"""
        cache_key = url
        if use_cache and cache_key in self.cache:
            if time.time() - self.cache[cache_key]['timestamp'] < 300:  # 5 minutos de cache
                return self.cache[cache_key]['response']
        
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            
            if use_cache:
                self.cache[cache_key] = {
                    'response': response,
                    'timestamp': time.time()
                }
            
            return response
        except Exception as e:
            st.error(f"Erro ao acessar {url}: {e}")
            return None
    
    def construir_url_busca(self, id_curso, departamento=None, periodo='20252'):
        """Constrói URL de busca para o quadro de horários"""
        params = {
            'utf8': '✓',
            'q[anosemestre_eq]': periodo,
            'q[disciplina_cod_departamento_eq]': '',
            'button': '',
            'q[idturno_eq]': '',
            'q[idlocalidade_eq]': '',
            'q[vagas_turma_curso_idcurso_eq]': id_curso,
            'q[disciplina_disciplinas_curriculos_idcurriculo_eq]': '',
            'q[curso_ferias_eq]': '',
            'q[idturmamodalidade_eq]': ''
        }
        
        if departamento and departamento.strip():
            params['q[disciplina_nome_or_disciplina_codigo_cont]'] = f"{departamento.strip().upper()}00"
        else:
            params['q[disciplina_nome_or_disciplina_codigo_cont]'] = ''
        
        # Construir URL com parâmetros
        url = self.base_url + "?"
        url_parts = []
        for key, value in params.items():
            url_parts.append(f"{key}={value}")
        
        return url + "&".join(url_parts)
    
    def extrair_turmas_da_pagina(self, html_content):
        """Extrai informações das turmas de uma página HTML"""
        turmas = []
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Encontrar tabela de turmas
        tabela = soup.find('table', class_='table')
        
        if not tabela:
            return turmas
        
        # Extrair linhas da tabela
        linhas = tabela.find_all('tr')[1:]  # Pular cabeçalho
        
        for linha in linhas:
            colunas = linha.find_all('td')
            if len(colunas) >= 8:  # Verificar se tem colunas suficientes
                try:
                    # Extrair informações básicas
                    codigo = colunas[0].get_text(strip=True)
                    nome = colunas[1].get_text(strip=True)
                    turma = colunas[2].get_text(strip=True)
                    
                    # Extrair vagas disponíveis (simplificado)
                    vagas_texto = colunas[5].get_text(strip=True)
                    vagas_match = re.search(r'(\d+)/(\d+)', vagas_texto)
                    
                    if vagas_match:
                        vagas_ocupadas = int(vagas_match.group(1))
                        vagas_totais = int(vagas_match.group(2))
                        vagas_disponiveis = vagas_totais - vagas_ocupadas
                    else:
                        vagas_disponiveis = 0
                        vagas_totais = 0
                    
                    # Extrair link para detalhes da turma
                    link_tag = colunas[0].find('a')
                    link = link_tag['href'] if link_tag else ''
                    if link and not link.startswith('http'):
                        link = f"https://app.uff.br{link}"
                    
                    turma_info = {
                        'codigo': codigo,
                        'nome': nome,
                        'turma': turma,
                        'vagas_totais': vagas_totais,
                        'vagas_disponiveis': vagas_disponiveis,
                        'link': link,
                        'departamento': codigo[:3] if len(codigo) >= 3 else '',
                        'periodo': ''
                    }
                    
                    turmas.append(turma_info)
                    
                except Exception as e:
                    continue
        
        return turmas
    
    def buscar_turmas_por_filtro(self, curso_nome, periodo, departamento=None):
        """Busca turmas com base nos filtros"""
        st.info(f"🔍 Buscando turmas de {curso_nome} - Período {periodo}" + 
               (f" - Depto {departamento}" if departamento else ""))
        
        # Obter ID do curso
        id_curso = self.ids_cursos.get(curso_nome)
        if not id_curso:
            st.error(f"Curso {curso_nome} não encontrado!")
            return []
        
        # Construir URL de busca
        url = self.construir_url_busca(id_curso, departamento, periodo)
        
        # Fazer requisição
        response = self.fazer_request(url)
        if not response:
            return []
        
        # Extrair turmas da primeira página
        todas_turmas = self.extrair_turmas_da_pagina(response.content)
        
        # Tentar buscar páginas adicionais (simplificado - apenas primeira página)
        # Nota: Em produção, você pode implementar paginação completa
        
        return todas_turmas
    
    def consultar_vagas_avancado(self, periodos, cursos, departamentos):
        """Consulta avançada de vagas"""
        todas_turmas = []
        
        # Barra de progresso
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        total_consultas = len(periodos) * len(cursos) * len(departamentos)
        consulta_atual = 0
        
        for periodo in periodos:
            for curso in cursos:
                for depto in departamentos:
                    if st.session_state.processando == False:
                        return todas_turmas
                    
                    consulta_atual += 1
                    progresso = consulta_atual / total_consultas
                    progress_bar.progress(progresso)
                    status_text.text(f"Consultando: {curso} - {periodo} - {depto or 'Todos'}")
                    
                    # Buscar turmas
                    turmas = self.buscar_turmas_por_filtro(curso, periodo, depto)
                    
                    # Adicionar informações extras
                    for turma in turmas:
                        turma['periodo'] = periodo
                        turma['curso'] = curso
                        turma['departamento_filtro'] = depto or 'Todos'
                    
                    todas_turmas.extend(turmas)
                    
                    # Pequena pausa para não sobrecarregar o servidor
                    time.sleep(1)
        
        progress_bar.empty()
        status_text.empty()
        
        return todas_turmas

# ===== FUNÇÕES AUXILIARES =====
def formatar_periodo(periodo):
    """Formata o período para exibição"""
    if len(periodo) == 5:
        ano = periodo[:4]
        semestre = periodo[4]
        return f"{ano}.{semestre}"
    return periodo

def obter_departamentos_disponiveis():
    """Retorna lista de departamentos disponíveis"""
    return [
        'TODOS', 'GQI', 'GFI', 'MAF', 'GEC', 'GEO', 'GEA',
        'GFB', 'GCN', 'GCO', 'GMN', 'GPR', 'FIS', 'BIO'
    ]

def criar_visualizacoes(df):
    """Cria visualizações dos dados"""
    if df.empty:
        return None
    
    # Criar abas para diferentes visualizações
    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 Visão Geral",
        "📈 Estatísticas por Curso",
        "🏫 Vagas por Departamento",
        "📅 Evolução por Período"
    ])
    
    with tab1:
        # Métricas gerais
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            total_turmas = len(df)
            st.metric("Total de Turmas", total_turmas)
        
        with col2:
            turmas_com_vagas = len(df[df['vagas_disponiveis'] > 0])
            st.metric("Turmas com Vagas", turmas_com_vagas)
        
        with col3:
            total_vagas = df['vagas_disponiveis'].sum()
            st.metric("Vagas Disponíveis", total_vagas)
        
        with col4:
            taxa_ocupacao = (1 - (total_vagas / df['vagas_totais'].sum())) * 100 if df['vagas_totais'].sum() > 0 else 0
            st.metric("Taxa de Ocupação", f"{taxa_ocupacao:.1f}%")
        
        # Gráfico de vagas por curso
        st.subheader("Vagas Disponíveis por Curso")
        vagas_por_curso = df.groupby('curso')['vagas_disponiveis'].sum().reset_index()
        
        if not vagas_por_curso.empty:
            fig = px.bar(vagas_por_curso, 
                        x='curso', 
                        y='vagas_disponiveis',
                        color='curso',
                        color_discrete_map={
                            'Química': '#FFE6CC',
                            'Química Industrial': '#E6F3FF'
                        })
            fig.update_layout(height=400)
            st.plotly_chart(fig, use_container_width=True)
    
    with tab2:
        # Estatísticas detalhadas por curso
        for curso in df['curso'].unique():
            st.subheader(f"📋 {curso}")
            df_curso = df[df['curso'] == curso]
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("Turmas", len(df_curso))
            
            with col2:
                vagas_curso = df_curso['vagas_disponiveis'].sum()
                st.metric("Vagas Disponíveis", vagas_curso)
            
            with col3:
                ocupacao_curso = (1 - (vagas_curso / df_curso['vagas_totais'].sum())) * 100 if df_curso['vagas_totais'].sum() > 0 else 0
                st.metric("Ocupação", f"{ocupacao_curso:.1f}%")
            
            # Top 5 disciplinas com mais vagas
            top_vagas = df_curso.nlargest(5, 'vagas_disponiveis')[['nome', 'vagas_disponiveis', 'departamento']]
            if not top_vagas.empty:
                st.write("**Top 5 disciplinas com mais vagas:**")
                st.dataframe(top_vagas, hide_index=True, use_container_width=True)
    
    with tab3:
        # Vagas por departamento
        st.subheader("Distribuição por Departamento")
        
        vagas_depto = df.groupby('departamento').agg({
            'codigo': 'count',
            'vagas_disponiveis': 'sum'
        }).reset_index()
        vagas_depto.columns = ['Departamento', 'Turmas', 'Vagas Disponíveis']
        
        if not vagas_depto.empty:
            # Gráfico de treemap
            fig = px.treemap(vagas_depto, 
                           path=['Departamento'],
                           values='Vagas Disponíveis',
                           color='Turmas',
                           color_continuous_scale='Blues',
                           title='Vagas por Departamento')
            fig.update_layout(height=500)
            st.plotly_chart(fig, use_container_width=True)
            
            # Tabela detalhada
            st.write("**Detalhamento por departamento:**")
            st.dataframe(vagas_depto.sort_values('Vagas Disponíveis', ascending=False), 
                        hide_index=True, use_container_width=True)
    
    with tab4:
        # Evolução por período (se houver múltiplos períodos)
        periodos_unicos = df['periodo'].unique()
        if len(periodos_unicos) > 1:
            st.subheader("Evolução por Período")
            
            evolucao = df.groupby(['periodo', 'curso']).agg({
                'codigo': 'count',
                'vagas_disponiveis': 'sum'
            }).reset_index()
            
            fig = px.line(evolucao, 
                         x='periodo', 
                         y='vagas_disponiveis',
                         color='curso',
                         markers=True,
                         title='Vagas Disponíveis por Período')
            fig.update_layout(height=400)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Adicione mais períodos para ver a evolução temporal.")

def exportar_para_excel(df):
    """Exporta dados para Excel formatado"""
    if df.empty:
        return None
    
    # Criar DataFrame com colunas ordenadas
    colunas_export = [
        'periodo', 'departamento', 'codigo', 'nome', 'turma',
        'vagas_totais', 'vagas_disponiveis', 'curso', 'link'
    ]
    
    df_export = df[colunas_export].copy()
    df_export['periodo'] = df_export['periodo'].apply(formatar_periodo)
    
    # Renomear colunas
    df_export.columns = [
        'Período', 'Departamento', 'Código', 'Disciplina', 'Turma',
        'Vagas Totais', 'Vagas Disponíveis', 'Curso', 'Link'
    ]
    
    # Ordenar
    df_export = df_export.sort_values(['Período', 'Departamento', 'Código', 'Turma'])
    
    # Criar Excel em memória
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        # Aba principal
        df_export.to_excel(writer, sheet_name='Todas as Turmas', index=False)
        
        # Abas filtradas
        for curso in df_export['Curso'].unique():
            df_curso = df_export[df_export['Curso'] == curso]
            df_curso.to_excel(writer, sheet_name=curso[:30], index=False)
        
        # Aba com vagas
        df_vagas = df_export[df_export['Vagas Disponíveis'] > 0]
        if not df_vagas.empty:
            df_vagas.to_excel(writer, sheet_name='Com Vagas', index=False)
        
        # Aba de estatísticas
        stats_data = []
        for periodo in df_export['Período'].unique():
            df_periodo = df_export[df_export['Período'] == periodo]
            for curso in df_periodo['Curso'].unique():
                df_curso_periodo = df_periodo[df_periodo['Curso'] == curso]
                
                stats_data.append({
                    'Período': periodo,
                    'Curso': curso,
                    'Turmas': len(df_curso_periodo),
                    'Turmas com Vagas': len(df_curso_periodo[df_curso_periodo['Vagas Disponíveis'] > 0]),
                    'Vagas Totais': df_curso_periodo['Vagas Totais'].sum(),
                    'Vagas Disponíveis': df_curso_periodo['Vagas Disponíveis'].sum(),
                    'Taxa Ocupação (%)': round((1 - (df_curso_periodo['Vagas Disponíveis'].sum() / df_curso_periodo['Vagas Totais'].sum())) * 100, 2) 
                    if df_curso_periodo['Vagas Totais'].sum() > 0 else 0
                })
        
        stats_df = pd.DataFrame(stats_data)
        stats_df.to_excel(writer, sheet_name='Estatísticas', index=False)
    
    output.seek(0)
    return output

# ===== INTERFACE PRINCIPAL =====
st.markdown('<p class="main-header">Consultor de Vagas UFF - Instituto de Química</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-header">Sistema de consulta de turmas e vagas disponíveis</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-header">Desenvolvido por <strong>Tadeu L. Araújo</strong> (GGQ)</p>', unsafe_allow_html=True)

# Sidebar com filtros
with st.sidebar:
    st.header("⚙️ Configurações da Consulta")
    
    st.markdown("---")
    st.subheader("📅 Períodos Letivos")
    
    # Períodos disponíveis
    periodos_opcoes = ['2025.2', '2025.1', '2024.2', '2024.1']
    periodos_selecionados = st.multiselect(
        "Selecione os períodos:",
        options=periodos_opcoes,
        default=['2025.2']
    )
    
    # Converter para formato interno
    periodos_formatados = [p.replace('.', '') for p in periodos_selecionados]
    
    st.markdown("---")
    st.subheader("🎓 Cursos")
    
    cursos_selecionados = st.multiselect(
        "Selecione os cursos:",
        options=['Química', 'Química Industrial'],
        default=['Química', 'Química Industrial']
    )
    
    st.markdown("---")
    st.subheader("🏫 Departamentos")
    
    departamentos_opcoes = obter_departamentos_disponiveis()
    departamentos_selecionados = st.multiselect(
        "Filtrar por departamento:",
        options=departamentos_opcoes,
        default=['TODOS']
    )
    
    # Converter departamentos
    if 'TODOS' in departamentos_selecionados:
        departamentos_consulta = [None] + [d for d in departamentos_selecionados if d != 'TODOS']
    else:
        departamentos_consulta = departamentos_selecionados
    
    st.markdown("---")
    
    # Botão de consulta
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔍 Consultar Vagas", type="primary", use_container_width=True):
            if not periodos_formatados:
                st.error("Selecione pelo menos um período!")
            elif not cursos_selecionados:
                st.error("Selecione pelo menos um curso!")
            else:
                st.session_state.processando = True
                st.session_state.resultado_disponivel = False
                st.session_state.periodo_selecionado = periodos_selecionados
    
    with col2:
        if st.button("🔄 Limpar Consulta", use_container_width=True):
            st.session_state.processando = False
            st.session_state.resultado_disponivel = False
            st.session_state.dados_turmas = None
            st.rerun()
    
    st.markdown("---")
    st.info("""
    **💡 Dicas:**
    - A consulta pode levar alguns minutos
    - Use filtros para resultados mais específicos
    - Dados atualizados do sistema UFF
    """)

# Área principal
if st.session_state.processando:
    st.info("🔄 **Consultando dados do sistema UFF...**")
    st.warning("⏳ Esta operação pode levar alguns minutos. Por favor, aguarde.")
    
    try:
        # Inicializar consultor
        consultor = ConsultorQuadroHorariosUFFStreamlit()
        
        # Executar consulta
        dados = consultor.consultar_vagas_avancado(
            periodos=periodos_formatados,
            cursos=cursos_selecionados,
            departamentos=departamentos_consulta
        )
        
        if dados:
            st.session_state.dados_turmas = pd.DataFrame(dados)
            st.session_state.resultado_disponivel = True
            st.session_state.processando = False
            
            st.success(f"✅ Consulta concluída! {len(dados)} turmas encontradas.")
            st.rerun()
        else:
            st.error("❌ Nenhuma turma encontrada com os filtros selecionados.")
            st.session_state.processando = False
    
    except Exception as e:
        st.error(f"❌ Erro durante a consulta: {str(e)}")
        st.session_state.processando = False

# Mostrar resultados se disponível
if st.session_state.resultado_disponivel and st.session_state.dados_turmas is not None:
    df = st.session_state.dados_turmas
    
    st.markdown("---")
    st.subheader(f"📋 Resultados da Consulta")
    
    # Mostrar estatísticas rápidas
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Períodos", len(df['periodo'].unique()))
    
    with col2:
        st.metric("Cursos", len(df['curso'].unique()))
    
    with col3:
        st.metric("Turmas com Vagas", len(df[df['vagas_disponiveis'] > 0]))
    
    # Criar visualizações
    criar_visualizacoes(df)
    
    # Opções de exportação
    st.markdown("---")
    st.subheader("📥 Exportar Resultados")
    
    col_export1, col_export2 = st.columns(2)
    
    with col_export1:
        # Exportar para Excel
        if st.button("📊 Exportar para Excel", use_container_width=True):
            excel_buffer = exportar_para_excel(df)
            if excel_buffer:
                st.download_button(
                    label="⬇️ Baixar Planilha Excel",
                    data=excel_buffer,
                    file_name=f"vagas_uff_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
    
    with col_export2:
        # Exportar para CSV
        if st.button("📄 Exportar para CSV", use_container_width=True):
            csv = df.to_csv(index=False, encoding='utf-8-sig')
            st.download_button(
                label="⬇️ Baixar CSV",
                data=csv,
                file_name=f"vagas_uff_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
                use_container_width=True
            )
    
    # Tabela completa interativa
    st.markdown("---")
    st.subheader("📋 Tabela Completa de Turmas")
    
    # Filtros interativos
    col_filtro1, col_filtro2, col_filtro3 = st.columns(3)
    
    with col_filtro1:
        filtro_curso = st.selectbox(
            "Filtrar por curso:",
            options=['Todos'] + list(df['curso'].unique())
        )
    
    with col_filtro2:
        filtro_depto = st.selectbox(
            "Filtrar por departamento:",
            options=['Todos'] + list(df['departamento'].unique())
        )
    
    with col_filtro3:
        filtro_vagas = st.selectbox(
            "Filtrar por vagas:",
            options=['Todas', 'Com vagas disponíveis', 'Sem vagas']
        )
    
    # Aplicar filtros
    df_filtrado = df.copy()
    
    if filtro_curso != 'Todos':
        df_filtrado = df_filtrado[df_filtrado['curso'] == filtro_curso]
    
    if filtro_depto != 'Todos':
        df_filtrado = df_filtrado[df_filtrado['departamento'] == filtro_depto]
    
    if filtro_vagas == 'Com vagas disponíveis':
        df_filtrado = df_filtrado[df_filtrado['vagas_disponiveis'] > 0]
    elif filtro_vagas == 'Sem vagas':
        df_filtrado = df_filtrado[df_filtrado['vagas_disponiveis'] == 0]
    
    # Mostrar tabela
    st.dataframe(
        df_filtrado[['periodo', 'curso', 'departamento', 'codigo', 'nome', 'turma', 
                    'vagas_totais', 'vagas_disponiveis', 'link']],
        column_config={
            "periodo": "Período",
            "curso": "Curso",
            "departamento": "Depto",
            "codigo": "Código",
            "nome": "Disciplina",
            "turma": "Turma",
            "vagas_totais": "Vagas Totais",
            "vagas_disponiveis": "Vagas Disp.",
            "link": st.column_config.LinkColumn("Link")
        },
        hide_index=True,
        use_container_width=True
    )
    
    st.info(f"Mostrando {len(df_filtrado)} de {len(df)} turmas")

# Página inicial (quando não há consulta em andamento)
elif not st.session_state.processando:
    st.markdown("---")
    
    col_intro1, col_intro2 = st.columns(2)
    
    with col_intro1:
        st.markdown("""
        ## 🎯 Sobre o Sistema
        
        Este sistema consulta automaticamente as vagas disponíveis
        nas disciplinas do **Instituto de Química da UFF**.
        
        **Funcionalidades:**
        - ✅ Consulta em tempo real do quadro de horários
        - ✅ Filtros por período, curso e departamento
        - ✅ Visualizações interativas e gráficos
        - ✅ Exportação para Excel/CSV
        - ✅ Identificação de turmas com vagas
        
        **Cursos suportados:**
        - 🧪 Bacharelado em Química
        - 🏭 Bacharelado em Química Industrial
        """)
    
    with col_intro2:
        st.markdown("""
        ## 📋 Como Usar
        
        1. **Selecione os períodos** letivos na barra lateral
        2. **Escolha os cursos** que deseja consultar
        3. **Filtre por departamentos** (opcional)
        4. **Clique em "Consultar Vagas"**
        5. **Analise os resultados** e exporte se necessário
        
        ## ⚠️ Limitações
        
        - A consulta depende da disponibilidade do sistema UFF
        - Dados são atualizados conforme a publicação oficial
        - Algumas informações podem estar sujeitas a alterações
        
        ## 🆘 Suporte
        
        Em caso de problemas ou dúvidas, entre em contato.
        """)
    
    st.markdown("---")
    
    # Exemplo de dados (para demonstração)
    with st.expander("👁️ **Visualizar exemplo de dados**"):
        st.markdown("""
        **Estrutura dos dados coletados:**
        
        | Período | Curso | Departamento | Código | Disciplina | Turma | Vagas Totais | Vagas Disp. |
        |---------|-------|--------------|--------|------------|-------|--------------|-------------|
        | 2025.2  | Química | GQI | GQI0001 | Química Geral | A01 | 60 | 5 |
        | 2025.2  | Química Ind. | GFI | GFI0002 | Química Orgânica | B02 | 40 | 0 |
        | 2025.1  | Química | MAF | MAF0003 | Físico-Química | C03 | 50 | 12 |
        
        *Dados de exemplo para ilustração*
        """)

# ===== RODAPÉ =====
st.markdown("---")
st.markdown(
    "<div style='text-align: center; color: #666; font-size: 0.9rem;'>"
    "Desenvolvido por Tadeu L. Araújo (GGQ) • Instituto de Química - UFF • "
    f"Última atualização: {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    "</div>",
    unsafe_allow_html=True
)
