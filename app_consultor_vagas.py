# ==============================================
# CONSULTOR DE VAGAS UFF - VERSÃO STREAMLIT CORRIGIDA
# Sistema de consulta detalhada de turmas e vagas
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
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils.dataframe import dataframe_to_rows
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
    .stProgress > div > div > div > div {
        background-color: #1e3a5f;
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
if 'apenas_cursos_quimica' not in st.session_state:
    st.session_state.apenas_cursos_quimica = True

# ===== CLASSE DE CONSULTA UFF DETALHADA (VERSÃO CORRIGIDA) =====
class ConsultorQuadroHorariosUFFDetalhado:
    def __init__(self, apenas_cursos_quimica=True):
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
        self.cache = {}
        self.apenas_cursos_quimica = apenas_cursos_quimica
        
        # Mapeamento de cursos
        self.ids_cursos = {
            'Química': '28',
            'Química Industrial': '29'
        }
        
        self.cores_cursos = {
            'Química': 'FFE6CC',
            'Química Industrial': 'E6F3FF'
        }
        
        # Códigos de cursos de química para filtro
        self.codigos_cursos_quimica = ['028', '029', 'Química', 'Química Industrial']
    
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
            st.warning(f"⚠️ Erro ao acessar {url}: {e}")
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
        
        if departamento and departamento.strip() and departamento != 'TODOS':
            params['q[disciplina_nome_or_disciplina_codigo_cont]'] = f"{departamento.strip().upper()}00"
        else:
            params['q[disciplina_nome_or_disciplina_codigo_cont]'] = ''
        
        # Construir URL
        url_parts = [f"{key}={value}" for key, value in params.items()]
        return self.base_url + "?" + "&".join(url_parts)
    
    def extrair_links_turmas_pagina(self, html_content):
        """Extrai links para páginas detalhadas das turmas"""
        soup = BeautifulSoup(html_content, 'html.parser')
        links = []
        
        # Encontrar tabela principal
        tabela = soup.find('table', class_='table')
        if tabela:
            for link in tabela.find_all('a', href=True):
                href = link['href']
                if '/turmas/' in href:
                    full_url = href if href.startswith('http') else f"https://app.uff.br{href}"
                    links.append(full_url)
        else:
            # Tentar encontrar links alternativamente
            for link in soup.find_all('a', href=True):
                href = link['href']
                if '/turmas/' in href and href not in links:
                    full_url = href if href.startswith('http') else f"https://app.uff.br{href}"
                    links.append(full_url)
        
        return list(set(links))
    
    def navegar_paginas(self, url_inicial, nome_curso):
        """Navega por todas as páginas de resultados"""
        todos_links = []
        pagina_atual = 1
        
        status_placeholder = st.empty()
        
        while True:
            url_pagina = f"{url_inicial}&page={pagina_atual}" if pagina_atual > 1 else url_inicial
            status_placeholder.text(f"📄 Buscando página {pagina_atual}...")
            
            response = self.fazer_request(url_pagina)
            
            if not response:
                break
            
            soup = BeautifulSoup(response.content, 'html.parser')
            links_pagina = self.extrair_links_turmas_pagina(response.content)
            
            if not links_pagina:
                break
            
            todos_links.extend(links_pagina)
            
            # Verificar se há próxima página
            pagination = soup.find('ul', class_='pagination')
            if not pagination:
                break
                
            next_disabled = pagination.find('li', class_='next disabled')
            if next_disabled:
                break
            
            pagina_atual += 1
            time.sleep(0.5)  # Respeitar o servidor
        
        status_placeholder.empty()
        return list(set(todos_links))
    
    def extrair_horarios_turma(self, soup):
        """Extrai horários da turma - VERSÃO CORRIGIDA"""
        try:
            # Procurar seção de horários
            secao_horarios = None
            for h in soup.find_all(['h2', 'h3', 'h4', 'h5', 'strong', 'b']):
                texto = h.get_text(strip=True).lower()
                if 'horários' in texto and 'turma' in texto:
                    secao_horarios = h
                    break
            
            if secao_horarios:
                # Encontrar tabela seguinte
                proximo_elemento = secao_horarios.find_next(['table', 'div'])
                if proximo_elemento and proximo_elemento.name == 'table':
                    tabela_horarios = proximo_elemento
                else:
                    # Tentar encontrar tabela depois do elemento
                    tabela_horarios = secao_horarios.find_next('table')
                
                if tabela_horarios:
                    horarios = []
                    dias_semana = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado']
                    
                    # Encontrar linha de horários (geralmente segunda linha)
                    linhas = tabela_horarios.find_all('tr')
                    if len(linhas) >= 2:
                        linha_horarios = linhas[1]  # Segunda linha geralmente tem os horários
                        colunas = linha_horarios.find_all(['td', 'th'])
                        
                        for i, coluna in enumerate(colunas):
                            if i >= len(dias_semana):
                                break
                            texto = coluna.get_text(strip=True)
                            if texto and texto not in dias_semana:
                                horarios.append(f"{dias_semana[i]}: {texto}")
                    
                    return ' | '.join(horarios) if horarios else 'Não informado'
        except Exception as e:
            st.warning(f"⚠️ Erro ao extrair horários: {e}")
        
        return 'Não informado'
    
    def extrair_vagas_detalhadas(self, soup, curso_origem):
        """Extrai vagas detalhadas da turma - FILTRO APENAS CURSOS QUÍMICA"""
        try:
            # Procurar tabela de vagas alocadas
            tabela_vagas = None
            
            # Método 1: Buscar por texto "Vagas Alocadas" e pegar a próxima tabela
            for elemento in soup.find_all(['h2', 'h3', 'h4', 'h5', 'strong', 'b']):
                texto = elemento.get_text(strip=True).lower()
                if 'vagas' in texto and 'alocadas' in texto:
                    # Encontrar a próxima tabela
                    for proximo in elemento.find_next_siblings():
                        if proximo.name == 'table':
                            tabela_vagas = proximo
                            break
                    if not tabela_vagas:
                        # Tentar encontrar qualquer tabela após o elemento
                        tabela_vagas = elemento.find_next('table')
                    break
            
            # Método 2: Buscar tabela com estrutura específica
            if not tabela_vagas:
                for tabela in soup.find_all('table'):
                    texto_tabela = tabela.get_text(strip=True).lower()
                    if 'vagas' in texto_tabela and ('reg' in texto_tabela or 'vest' in texto_tabela):
                        tabela_vagas = tabela
                        break
            
            if not tabela_vagas:
                return []  # Retorna lista vazia se não encontrar tabela
            
            vagas_encontradas = []
            texto_completo = tabela_vagas.get_text()
            
            # Procurar por cursos de química no texto completo
            cursos_encontrados = []
            
            # Padrão para Química (028)
            padrao_quimica = re.search(r'(028.*?Química).*?(\d+).*?(\d+).*?(\d+).*?(\d+)', texto_completo, re.IGNORECASE | re.DOTALL)
            if padrao_quimica:
                nome_curso = padrao_quimica.group(1).strip()
                vagas_reg = int(padrao_quimica.group(2)) if padrao_quimica.group(2).isdigit() else 0
                vagas_vest = int(padrao_quimica.group(3)) if padrao_quimica.group(3).isdigit() else 0
                inscritos_reg = int(padrao_quimica.group(4)) if padrao_quimica.group(4).isdigit() else 0
                inscritos_vest = int(padrao_quimica.group(5)) if padrao_quimica.group(5).isdigit() else 0
                
                # Se filtro ativo, só inclui se for curso de química
                if not self.apenas_cursos_quimica or 'química' in nome_curso.lower():
                    vaga_info = {
                        'curso': nome_curso,
                        'vagas_reg': vagas_reg,
                        'vagas_vest': vagas_vest,
                        'inscritos_reg': inscritos_reg,
                        'inscritos_vest': inscritos_vest,
                        'excedentes': 0,
                        'candidatos': 0,
                        'vagas_disponiveis_reg': max(0, vagas_reg - inscritos_reg),
                        'vagas_disponiveis_vest': max(0, vagas_vest - inscritos_vest),
                        'total_vagas': vagas_reg + vagas_vest,
                        'total_inscritos': inscritos_reg + inscritos_vest,
                        'total_vagas_disponiveis': max(0, (vagas_reg - inscritos_reg) + (vagas_vest - inscritos_vest))
                    }
                    vagas_encontradas.append(vaga_info)
            
            # Padrão para Química Industrial (029)
            padrao_industrial = re.search(r'(029.*?Química.*?Industrial).*?(\d+).*?(\d+).*?(\d+).*?(\d+)', texto_completo, re.IGNORECASE | re.DOTALL)
            if padrao_industrial:
                nome_curso = padrao_industrial.group(1).strip()
                vagas_reg = int(padrao_industrial.group(2)) if padrao_industrial.group(2).isdigit() else 0
                vagas_vest = int(padrao_industrial.group(3)) if padrao_industrial.group(3).isdigit() else 0
                inscritos_reg = int(padrao_industrial.group(4)) if padrao_industrial.group(4).isdigit() else 0
                inscritos_vest = int(padrao_industrial.group(5)) if padrao_industrial.group(5).isdigit() else 0
                
                # Se filtro ativo, só inclui se for curso de química
                if not self.apenas_cursos_quimica or 'química' in nome_curso.lower():
                    vaga_info = {
                        'curso': nome_curso,
                        'vagas_reg': vagas_reg,
                        'vagas_vest': vagas_vest,
                        'inscritos_reg': inscritos_reg,
                        'inscritos_vest': inscritos_vest,
                        'excedentes': 0,
                        'candidatos': 0,
                        'vagas_disponiveis_reg': max(0, vagas_reg - inscritos_reg),
                        'vagas_disponiveis_vest': max(0, vagas_vest - inscritos_vest),
                        'total_vagas': vagas_reg + vagas_vest,
                        'total_inscritos': inscritos_reg + inscritos_vest,
                        'total_vagas_disponiveis': max(0, (vagas_reg - inscritos_reg) + (vagas_vest - inscritos_vest))
                    }
                    vagas_encontradas.append(vaga_info)
            
            # Se não encontrou por regex, tentar método alternativo
            if not vagas_encontradas:
                # Extrair linhas da tabela
                linhas = tabela_vagas.find_all('tr')
                
                for linha in linhas:
                    texto_linha = linha.get_text(strip=True).lower()
                    
                    # Verificar se é linha de curso de química
                    if ('028' in texto_linha or '029' in texto_linha or 
                        'química' in texto_linha):
                        
                        # Extrair números da linha
                        numeros = re.findall(r'\d+', linha.get_text())
                        
                        if len(numeros) >= 4:
                            try:
                                nome_curso_match = re.search(r'([A-Za-zÀ-ÿ\s\-]+)', linha.get_text())
                                nome_curso = nome_curso_match.group(1).strip() if nome_curso_match else "Curso não identificado"
                                
                                vagas_reg = int(numeros[0]) if len(numeros) > 0 else 0
                                vagas_vest = int(numeros[1]) if len(numeros) > 1 else 0
                                inscritos_reg = int(numeros[2]) if len(numeros) > 2 else 0
                                inscritos_vest = int(numeros[3]) if len(numeros) > 3 else 0
                                
                                # Se filtro ativo, só inclui se for curso de química
                                if not self.apenas_cursos_quimica or 'química' in nome_curso.lower():
                                    vaga_info = {
                                        'curso': nome_curso,
                                        'vagas_reg': vagas_reg,
                                        'vagas_vest': vagas_vest,
                                        'inscritos_reg': inscritos_reg,
                                        'inscritos_vest': inscritos_vest,
                                        'excedentes': 0,
                                        'candidatos': 0,
                                        'vagas_disponiveis_reg': max(0, vagas_reg - inscritos_reg),
                                        'vagas_disponiveis_vest': max(0, vagas_vest - inscritos_vest),
                                        'total_vagas': vagas_reg + vagas_vest,
                                        'total_inscritos': inscritos_reg + inscritos_vest,
                                        'total_vagas_disponiveis': max(0, (vagas_reg - inscritos_reg) + (vagas_vest - inscritos_vest))
                                    }
                                    vagas_encontradas.append(vaga_info)
                            except Exception as e:
                                continue
            
            return vagas_encontradas
            
        except Exception as e:
            st.warning(f"⚠️ Erro ao extrair vagas: {e}")
            return []
    
    def extrair_dados_turma_detalhado(self, url_turma, curso_origem, periodo, departamento_busca=None):
        """Extrai dados detalhados de uma turma específica - SEM DUPLICAÇÃO"""
        try:
            response = self.fazer_request(url_turma)
            if not response:
                return []
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extrair informações básicas do título
            titulo = soup.find('h1')
            codigo_disciplina = ''
            nome_disciplina = ''
            turma = ''
            departamento = ''
            
            if titulo:
                texto_titulo = titulo.get_text(strip=True)
                # Padrões possíveis para o título
                padroes = [
                    r'Turma\s+(\S+)\s+de\s+(\S+)\s+-\s+(.+)',  # Turma K1 de MAF00052 - Toxicologia Ocupacional
                    r'(\S+)\s+-\s+(.+)\s+-\s+Turma\s+(\S+)',   # MAF00052 - Toxicologia Ocupacional - Turma K1
                    r'(.+?)\s*-\s*Turma\s+(\S+)'              # Toxicologia Ocupacional - Turma K1
                ]
                
                for padrao in padroes:
                    match = re.search(padrao, texto_titulo)
                    if match:
                        if 'Turma' in padrao and 'de' in padrao:
                            turma = match.group(1)
                            codigo_disciplina = match.group(2)
                            nome_disciplina = match.group(3)
                        elif 'Turma' in padrao:
                            codigo_disciplina = match.group(1)
                            nome_disciplina = match.group(2)
                            turma = match.group(3) if len(match.groups()) > 2 else ''
                        break
                
                # Se não encontrou pelo padrão, tentar extrair de outra forma
                if not codigo_disciplina:
                    partes = texto_titulo.split(' - ')
                    if len(partes) >= 2:
                        primeira_parte = partes[0]
                        if 'Turma' in primeira_parte:
                            turma_match = re.search(r'Turma\s+(\S+)', primeira_parte)
                            if turma_match:
                                turma = turma_match.group(1)
                                if len(partes) > 1:
                                    segunda_parte = partes[1]
                                    if len(segunda_parte.split()) > 1:
                                        partes_codigo = segunda_parte.split()
                                        codigo_disciplina = partes_codigo[0]
                                        nome_disciplina = ' '.join(partes_codigo[1:]) if len(partes_codigo) > 1 else segunda_parte
                        
                departamento = codigo_disciplina[:3] if len(codigo_disciplina) >= 3 else ''
            
            # Filtrar por departamento se especificado
            if departamento_busca and departamento_busca != 'TODOS' and departamento != departamento_busca:
                return []
            
            # Extrair horários
            horarios = self.extrair_horarios_turma(soup)
            
            # Extrair vagas detalhadas
            vagas_detalhadas = self.extrair_vagas_detalhadas(soup, curso_origem)
            
            if not vagas_detalhadas:
                # Se não encontrou vagas E estamos filtrando apenas cursos química,
                # não retornar registro para evitar duplicação
                if self.apenas_cursos_quimica:
                    return []
                
                # Se não está filtrando, criar registro básico
                registro_basico = {
                    'periodo': periodo,
                    'departamento': departamento,
                    'codigo_disciplina': codigo_disciplina,
                    'nome_disciplina': nome_disciplina,
                    'turma': turma,
                    'horarios': horarios,
                    'curso_origem_busca': curso_origem,
                    'curso_vaga': curso_origem,
                    'vagas_reg': 0,
                    'vagas_vest': 0,
                    'inscritos_reg': 0,
                    'inscritos_vest': 0,
                    'excedentes': 0,
                    'candidatos': 0,
                    'vagas_disponiveis_reg': 0,
                    'vagas_disponiveis_vest': 0,
                    'total_vagas': 0,
                    'total_inscritos': 0,
                    'total_vagas_disponiveis': 0,
                    'url': url_turma
                }
                return [registro_basico]
            
            # Processar cada vaga encontrada
            registros = []
            for vaga in vagas_detalhadas:
                registro = {
                    'periodo': periodo,
                    'departamento': departamento,
                    'codigo_disciplina': codigo_disciplina,
                    'nome_disciplina': nome_disciplina,
                    'turma': turma,
                    'horarios': horarios,
                    'curso_origem_busca': curso_origem,
                    'curso_vaga': vaga['curso'],
                    'vagas_reg': vaga['vagas_reg'],
                    'vagas_vest': vaga['vagas_vest'],
                    'inscritos_reg': vaga['inscritos_reg'],
                    'inscritos_vest': vaga['inscritos_vest'],
                    'excedentes': vaga['excedentes'],
                    'candidatos': vaga['candidatos'],
                    'vagas_disponiveis_reg': vaga['vagas_disponiveis_reg'],
                    'vagas_disponiveis_vest': vaga['vagas_disponiveis_vest'],
                    'total_vagas': vaga['total_vagas'],
                    'total_inscritos': vaga['total_inscritos'],
                    'total_vagas_disponiveis': vaga['total_vagas_disponiveis'],
                    'url': url_turma
                }
                registros.append(registro)
            
            return registros
            
        except Exception as e:
            st.warning(f"⚠️ Erro ao processar turma {url_turma}: {e}")
            return []
    
    def buscar_turmas_detalhadas(self, curso_nome, periodo, departamento=None):
        """Busca turmas detalhadas com todos os dados"""
        st.info(f"🔍 Buscando turmas de {curso_nome} - Período {periodo}" + 
               (f" - Depto {departamento}" if departamento and departamento != 'TODOS' else ""))
        
        id_curso = self.ids_cursos.get(curso_nome)
        if not id_curso:
            return []
        
        # Construir URL de busca
        url_busca = self.construir_url_busca(id_curso, departamento, periodo)
        
        # Obter todos os links das turmas
        links_turmas = self.navegar_paginas(url_busca, curso_nome)
        
        if not links_turmas:
            st.warning(f"ℹ️ Nenhuma turma encontrada para {curso_nome} no período {periodo}")
            return []
        
        # Processar cada turma detalhadamente
        todas_turmas = []
        total_turmas = len(links_turmas)
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        for i, link in enumerate(links_turmas):
            if st.session_state.processando == False:
                break
                
            status_text.text(f"📋 Processando turma {i+1}/{total_turmas}: {link.split('/')[-1]}")
            
            registros = self.extrair_dados_turma_detalhado(link, curso_nome, periodo, departamento)
            
            # Filtrar para evitar duplicação
            for registro in registros:
                # Verificar se já existe registro similar
                duplicado = False
                for existente in todas_turmas:
                    if (existente['codigo_disciplina'] == registro['codigo_disciplina'] and
                        existente['turma'] == registro['turma'] and
                        existente['curso_vaga'] == registro['curso_vaga']):
                        duplicado = True
                        break
                
                if not duplicado:
                    todas_turmas.append(registro)
            
            progress_bar.progress((i + 1) / total_turmas)
            
            # Pequena pausa para não sobrecarregar
            time.sleep(0.3)
        
        progress_bar.empty()
        status_text.empty()
        
        return todas_turmas
    
    def consultar_vagas_completas(self, periodos, cursos, departamentos):
        """Consulta completa de vagas com todos os detalhes - SEM DUPLICAÇÃO"""
        todas_turmas = []
        
        total_consultas = len(periodos) * len(cursos) * len(departamentos)
        consulta_atual = 0
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        for periodo in periodos:
            for curso in cursos:
                for depto in departamentos:
                    if st.session_state.processando == False:
                        return todas_turmas
                    
                    consulta_atual += 1
                    progresso = consulta_atual / total_consultas
                    progress_bar.progress(progresso)
                    
                    status_text.text(f"🔍 {curso} | 📅 {periodo} | 🏫 {depto or 'Todos'}")
                    
                    turmas = self.buscar_turmas_detalhadas(curso, periodo, depto)
                    
                    # Adicionar turmas, evitando duplicação
                    for turma in turmas:
                        duplicado = False
                        for existente in todas_turmas:
                            if (existente['codigo_disciplina'] == turma['codigo_disciplina'] and
                                existente['turma'] == turma['turma'] and
                                existente['curso_vaga'] == turma['curso_vaga'] and
                                existente['periodo'] == turma['periodo']):
                                duplicado = True
                                break
                        
                        if not duplicado:
                            todas_turmas.append(turma)
                    
                    # Pequena pausa entre consultas
                    time.sleep(0.5)
        
        progress_bar.empty()
        status_text.empty()
        
        return todas_turmas
    
    def testar_extracao_turma(self, url_turma):
        """Função para testar a extração de uma turma específica"""
        response = self.fazer_request(url_turma)
        if not response:
            return None
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Extrair título
        titulo = soup.find('h1')
        titulo_texto = titulo.get_text(strip=True) if titulo else "Sem título"
        
        # Extrair vagas
        vagas = self.extrair_vagas_detalhadas(soup, "Teste")
        
        # Extrair horários
        horarios = self.extrair_horarios_turma(soup)
        
        return {
            'titulo': titulo_texto,
            'vagas': vagas,
            'horarios': horarios,
            'html_preview': str(soup)[:2000]  # Primeiros 2000 caracteres do HTML
        }

# ===== FUNÇÃO DE TESTE =====
def testar_extracao_individual():
    """Testa a extração de uma turma específica"""
    st.markdown("---")
    st.subheader("🧪 Teste de Extração Individual")
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        url_teste = st.text_input(
            "URL da turma para teste:",
            value="https://app.uff.br/graduacao/quadrodehorarios/turmas/100000427249",
            help="Cole a URL completa de uma turma para testar a extração"
        )
    
    with col2:
        apenas_quimica = st.checkbox("Apenas Química", value=True, 
                                    help="Mostrar apenas cursos de Química")
    
    if st.button("🔬 Testar Extração", type="secondary"):
        if url_teste:
            with st.spinner("Testando extração..."):
                consultor = ConsultorQuadroHorariosUFFDetalhado(apenas_cursos_quimica=apenas_quimica)
                resultado = consultor.testar_extracao_turma(url_teste)
                
                if resultado:
                    st.success("✅ Extração concluída!")
                    
                    # Mostrar resultados
                    col_res1, col_res2 = st.columns(2)
                    
                    with col_res1:
                        st.markdown("**📋 Informações Extraídas:**")
                        st.write(f"**Título:** {resultado['titulo']}")
                        st.write(f"**Horários:** {resultado['horarios']}")
                        
                        if resultado['vagas']:
                            st.markdown("**🎓 Vagas Encontradas:**")
                            for vaga in resultado['vagas']:
                                st.write(f"- **{vaga['curso']}:**")
                                st.write(f"  Vagas Reg: {vaga['vagas_reg']} | Inscritos Reg: {vaga['inscritos_reg']}")
                                st.write(f"  Vagas Vest: {vaga['vagas_vest']} | Inscritos Vest: {vaga['inscritos_vest']}")
                                st.write(f"  Vagas Disp. Reg: {vaga['vagas_disponiveis_reg']}")
                                st.write(f"  Vagas Disp. Vest: {vaga['vagas_disponiveis_vest']}")
                        else:
                            st.warning("⚠️ Nenhuma vaga encontrada" + 
                                     (" (filtro 'Apenas Química' ativo)" if apenas_quimica else ""))
                    
                    with col_res2:
                        st.markdown("**🔍 HTML da Página (amostra):**")
                        st.code(resultado['html_preview'][:1000], language='html')
                else:
                    st.error("❌ Falha na extração")

# ===== FUNÇÕES PARA FORMATAÇÃO EXCEL =====
def aplicar_formatacao_excel(workbook):
    """Aplica formatação profissional ao Excel"""
    header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True, size=11)
    border = Border(left=Side(style='thin'), right=Side(style='thin'),
                   top=Side(style='thin'), bottom=Side(style='thin'))
    center_align = Alignment(horizontal='center', vertical='center', wrap_text=True)
    left_align = Alignment(horizontal='left', vertical='center', wrap_text=True)
    
    fill_quimica = PatternFill(start_color="FFE6CC", end_color="FFE6CC", fill_type="solid")
    fill_quimica_industrial = PatternFill(start_color="E6F3FF", end_color="E6F3FF", fill_type="solid")
    
    for sheet_name in workbook.sheetnames:
        ws = workbook[sheet_name]
        
        # Definir larguras das colunas
        col_widths = {
            'A': 12, 'B': 12, 'C': 18, 'D': 50, 'E': 10, 'F': 30,
            'G': 30, 'H': 12, 'I': 12, 'J': 12, 'K': 12, 'L': 12,
            'M': 12, 'N': 12, 'O': 12, 'P': 12, 'Q': 12, 'R': 12,
            'S': 12, 'T': 12, 'U': 80
        }
        
        for col, width in col_widths.items():
            ws.column_dimensions[col].width = width
        
        # Aplicar formatação às células
        for row in ws.iter_rows():
            for cell in row:
                if cell.value is not None:
                    cell.border = border
                    if cell.row == 1:  # Cabeçalho
                        cell.fill = header_fill
                        cell.font = header_font
                        cell.alignment = center_align
                    else:
                        # Verificar tipo de alinhamento
                        if cell.column in [1, 2, 3, 5, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]:
                            cell.alignment = center_align
                        else:
                            cell.alignment = left_align
        
        # Aplicar cores por curso
        if ws.max_row > 1:
            for row in range(2, ws.max_row + 1):
                curso_cell = ws.cell(row=row, column=7)  # Coluna G = curso_vaga
                if curso_cell.value:
                    curso_str = str(curso_cell.value)
                    if '028' in curso_str or ('Química' in curso_str and 'Industrial' not in curso_str):
                        fill_color = fill_quimica
                    elif '029' in curso_str or 'Química Industrial' in curso_str:
                        fill_color = fill_quimica_industrial
                    else:
                        fill_color = None
                    
                    if fill_color:
                        for col in range(1, ws.max_column + 1):
                            ws.cell(row=row, column=col).fill = fill_color

def gerar_excel_completo(df, periodo_str):
    """Gera Excel completo no formato do Colab"""
    if df.empty:
        return None
    
    # Criar workbook
    wb = Workbook()
    
    # Remover sheet padrão
    if 'Sheet' in wb.sheetnames:
        del wb['Sheet']
    
    # Ordenar colunas
    colunas_ordem = [
        'periodo', 'departamento', 'codigo_disciplina', 'nome_disciplina', 'turma', 'horarios',
        'curso_vaga', 'vagas_reg', 'vagas_vest', 'inscritos_reg', 'inscritos_vest',
        'vagas_disponiveis_reg', 'vagas_disponiveis_vest', 'excedentes', 'candidatos',
        'total_vagas', 'total_inscritos', 'total_vagas_disponiveis',
        'curso_origem_busca', 'url'
    ]
    
    # Garantir que todas as colunas existam
    for col in colunas_ordem:
        if col not in df.columns:
            df[col] = ''
    
    df = df[colunas_ordem]
    
    # 1. Aba: Todas as Turmas
    ws_todas = wb.create_sheet('Todas as Turmas')
    for r_idx, row in enumerate(dataframe_to_rows(df, index=False, header=True), 1):
        for c_idx, value in enumerate(row, 1):
            ws_todas.cell(row=r_idx, column=c_idx, value=value)
    
    # 2. Aba: Com Vagas Regulares
    df_vagas_reg = df[df['vagas_disponiveis_reg'] > 0]
    if not df_vagas_reg.empty:
        ws_vagas_reg = wb.create_sheet('Com Vagas Reg')
        for r_idx, row in enumerate(dataframe_to_rows(df_vagas_reg, index=False, header=True), 1):
            for c_idx, value in enumerate(row, 1):
                ws_vagas_reg.cell(row=r_idx, column=c_idx, value=value)
    
    # 3. Aba: Com Vagas Vestibular
    df_vagas_vest = df[df['vagas_disponiveis_vest'] > 0]
    if not df_vagas_vest.empty:
        ws_vagas_vest = wb.create_sheet('Com Vagas Vest')
        for r_idx, row in enumerate(dataframe_to_rows(df_vagas_vest, index=False, header=True), 1):
            for c_idx, value in enumerate(row, 1):
                ws_vagas_vest.cell(row=r_idx, column=c_idx, value=value)
    
    # 4. Aba: Por Departamento Detalhado
    if not df.empty:
        ws_depto = wb.create_sheet('Por Departamento')
        
        # Agrupar por departamento
        grupos = df.groupby(['periodo', 'departamento'])
        
        # Cabeçalhos
        headers = [
            'Período', 'Departamento', 'Código', 'Disciplina', 'Turma',
            'Vagas Reg', 'Vagas Vest', 'Inscritos Reg', 'Inscritos Vest',
            'Vagas Disp Reg', 'Vagas Disp Vest', 'Total Vagas', 'Total Inscritos', 'Total Vagas Disp'
        ]
        
        for col, header in enumerate(headers, 1):
            cell = ws_depto.cell(row=1, column=col, value=header)
            cell.fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
            cell.font = Font(color="FFFFFF", bold=True)
            cell.alignment = Alignment(horizontal='center')
        
        linha_atual = 2
        
        for (periodo, departamento), grupo in grupos:
            grupo = grupo.sort_values(['codigo_disciplina', 'turma'])
            
            for _, linha in grupo.iterrows():
                dados = [
                    periodo, departamento,
                    linha['codigo_disciplina'], linha['nome_disciplina'], linha['turma'],
                    linha['vagas_reg'], linha['vagas_vest'],
                    linha['inscritos_reg'], linha['inscritos_vest'],
                    linha['vagas_disponiveis_reg'], linha['vagas_disponiveis_vest'],
                    linha['total_vagas'], linha['total_inscritos'], linha['total_vagas_disponiveis']
                ]
                
                for col, valor in enumerate(dados, 1):
                    ws_depto.cell(row=linha_atual, column=col, value=valor)
                
                linha_atual += 1
    
    # 5. Aba: Estatísticas
    ws_stats = wb.create_sheet('Estatísticas')
    
    stats_data = []
    for periodo in df['periodo'].unique():
        df_periodo = df[df['periodo'] == periodo]
        
        for curso in df_periodo['curso_vaga'].unique():
            df_curso = df_periodo[df_periodo['curso_vaga'] == curso]
            
            stats_data.append({
                'Período': periodo,
                'Curso': curso,
                'Total Turmas': len(df_curso),
                'Turmas com Vagas Reg': len(df_curso[df_curso['vagas_disponiveis_reg'] > 0]),
                'Turmas com Vagas Vest': len(df_curso[df_curso['vagas_disponiveis_vest'] > 0]),
                'Total Vagas Reg': df_curso['vagas_reg'].sum(),
                'Total Vagas Vest': df_curso['vagas_vest'].sum(),
                'Total Inscritos Reg': df_curso['inscritos_reg'].sum(),
                'Total Inscritos Vest': df_curso['inscritos_vest'].sum(),
                'Total Vagas Disp Reg': df_curso['vagas_disponiveis_reg'].sum(),
                'Total Vagas Disp Vest': df_curso['vagas_disponiveis_vest'].sum(),
                'Taxa Ocupação Reg (%)': round((df_curso['inscritos_reg'].sum() / df_curso['vagas_reg'].sum() * 100), 2) if df_curso['vagas_reg'].sum() > 0 else 0,
                'Taxa Ocupação Vest (%)': round((df_curso['inscritos_vest'].sum() / df_curso['vagas_vest'].sum() * 100), 2) if df_curso['vagas_vest'].sum() > 0 else 0
            })
    
    if stats_data:
        stats_df = pd.DataFrame(stats_data)
        for r_idx, row in enumerate(dataframe_to_rows(stats_df, index=False, header=True), 1):
            for c_idx, value in enumerate(row, 1):
                ws_stats.cell(row=r_idx, column=c_idx, value=value)
    
    # Aplicar formatação
    aplicar_formatacao_excel(wb)
    
    # Salvar em buffer
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    
    return output

# ===== FUNÇÕES AUXILIARES =====
def formatar_periodo(periodo):
    """Formata período para exibição"""
    if '.' in periodo:
        return periodo
    elif len(periodo) == 5:
        return f"{periodo[:4]}.{periodo[4]}"
    return periodo

def validar_periodo(periodo):
    """Valida formato do período"""
    if '.' in periodo:
        partes = periodo.split('.')
        if len(partes) == 2 and partes[0].isdigit() and partes[1].isdigit():
            ano = int(partes[0])
            semestre = int(partes[1])
            if 2000 <= ano <= 2100 and semestre in [1, 2]:
                return True
    return False

def validar_departamento(depto):
    """Valida formato do departamento"""
    if depto == 'TODOS' or depto == '':
        return True
    if len(depto) == 3 and depto.isalpha():
        return True
    return False

def criar_visualizacoes(df):
    """Cria visualizações gráficas dos dados"""
    if df.empty:
        st.info("📭 Nenhum dado disponível para visualização")
        return
    
    tab1, tab2, tab3 = st.tabs(["📊 Visão Geral", "📈 Distribuição", "🏫 Análise Detalhada"])
    
    with tab1:
        # Métricas principais
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            total_turmas = len(df)
            st.metric("Total de Turmas", total_turmas)
        
        with col2:
            turmas_com_vagas = len(df[df['total_vagas_disponiveis'] > 0])
            st.metric("Turmas com Vagas", turmas_com_vagas)
        
        with col3:
            total_vagas_disp = df['total_vagas_disponiveis'].sum()
            st.metric("Vagas Disponíveis", total_vagas_disp)
        
        with col4:
            taxa_ocupacao = (1 - (total_vagas_disp / df['total_vagas'].sum())) * 100 if df['total_vagas'].sum() > 0 else 0
            st.metric("Taxa de Ocupação", f"{taxa_ocupacao:.1f}%")
        
        # Gráfico de vagas por curso
        st.subheader("📊 Vagas Disponíveis por Curso")
        
        vagas_curso = df.groupby('curso_vaga').agg({
            'vagas_disponiveis_reg': 'sum',
            'vagas_disponiveis_vest': 'sum'
        }).reset_index()
        
        if not vagas_curso.empty:
            fig = go.Figure()
            
            fig.add_trace(go.Bar(
                name='Vagas Regulares',
                x=vagas_curso['curso_vaga'],
                y=vagas_curso['vagas_disponiveis_reg'],
                marker_color='#1e3a5f'
            ))
            
            fig.add_trace(go.Bar(
                name='Vagas Vestibular',
                x=vagas_curso['curso_vaga'],
                y=vagas_curso['vagas_disponiveis_vest'],
                marker_color='#4a90e2'
            ))
            
            fig.update_layout(
                barmode='stack',
                height=400,
                title="Vagas Disponíveis por Tipo e Curso",
                xaxis_title="Curso",
                yaxis_title="Vagas Disponíveis",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            
            st.plotly_chart(fig, use_container_width=True)
    
    with tab2:
        # Distribuição por departamento
        st.subheader("🏫 Distribuição por Departamento")
        
        depto_dist = df.groupby('departamento').agg({
            'codigo_disciplina': 'count',
            'total_vagas_disponiveis': 'sum'
        }).reset_index()
        depto_dist.columns = ['Departamento', 'Número de Turmas', 'Vagas Disponíveis']
        
        if not depto_dist.empty:
            col1, col2 = st.columns(2)
            
            with col1:
                # Gráfico de treemap
                fig = px.treemap(
                    depto_dist,
                    path=['Departamento'],
                    values='Vagas Disponíveis',
                    color='Número de Turmas',
                    color_continuous_scale='Blues',
                    title='Vagas Disponíveis por Departamento'
                )
                fig.update_layout(height=500)
                st.plotly_chart(fig, use_container_width=True)
            
            with col2:
                # Tabela de departamentos
                st.write("**Ranking de Departamentos:**")
                depto_ranking = depto_dist.sort_values('Vagas Disponíveis', ascending=False)
                st.dataframe(
                    depto_ranking,
                    column_config={
                        "Departamento": st.column_config.TextColumn("Depto"),
                        "Número de Turmas": st.column_config.NumberColumn("Turmas"),
                        "Vagas Disponíveis": st.column_config.NumberColumn("Vagas Disp.")
                    },
                    hide_index=True,
                    use_container_width=True
                )
    
    with tab3:
        # Análise detalhada
        st.subheader("📋 Análise Detalhada por Disciplina")
        
        # Filtros para análise
        col_filt1, col_filt2 = st.columns(2)
        
        with col_filt1:
            curso_analise = st.selectbox(
                "Selecione o curso para análise:",
                options=['Todos'] + list(df['curso_vaga'].unique()),
                key="analise_curso"
            )
        
        with col_filt2:
            ordenacao = st.selectbox(
                "Ordenar por:",
                options=['Mais vagas disponíveis', 'Mais inscritos', 'Código da disciplina'],
                key="analise_ordenacao"
            )
        
        # Filtrar dados
        if curso_analise != 'Todos':
            df_analise = df[df['curso_vaga'] == curso_analise].copy()
        else:
            df_analise = df.copy()
        
        # Ordenar
        if ordenacao == 'Mais vagas disponíveis':
            df_analise = df_analise.sort_values('total_vagas_disponiveis', ascending=False)
        elif ordenacao == 'Mais inscritos':
            df_analise = df_analise.sort_values('total_inscritos', ascending=False)
        else:
            df_analise = df_analise.sort_values(['codigo_disciplina', 'turma'])
        
        # Mostrar tabela
        st.dataframe(
            df_analise[[
                'codigo_disciplina', 'nome_disciplina', 'turma', 'horarios',
                'vagas_reg', 'inscritos_reg', 'vagas_disponiveis_reg',
                'vagas_vest', 'inscritos_vest', 'vagas_disponiveis_vest',
                'total_vagas_disponiveis'
            ]].head(20),
            column_config={
                "codigo_disciplina": "Código",
                "nome_disciplina": "Disciplina",
                "turma": "Turma",
                "horarios": "Horários",
                "vagas_reg": "Vagas Reg",
                "inscritos_reg": "Inscritos Reg",
                "vagas_disponiveis_reg": "Disp. Reg",
                "vagas_vest": "Vagas Vest",
                "inscritos_vest": "Inscritos Vest",
                "vagas_disponiveis_vest": "Disp. Vest",
                "total_vagas_disponiveis": "Total Disp."
            },
            hide_index=True,
            use_container_width=True
        )

# ===== INTERFACE PRINCIPAL =====
st.markdown('<p class="main-header">Consultor de Vagas UFF - Instituto de Química</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-header">Sistema de consulta detalhada de turmas e vagas disponíveis</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-header">Desenvolvido por <strong>Tadeu L. Araújo</strong> (GGQ)</p>', unsafe_allow_html=True)

# Sidebar com filtros
with st.sidebar:
    st.header("⚙️ Configurações da Consulta")
    
    st.markdown("---")
    st.subheader("📅 Períodos Letivos")
    
    # Período com entrada livre
    periodo_input = st.text_input(
        "Digite o período (ex: 2025.2, 2026.1):",
        value="2025.2",
        help="Formato: AAAA.S (ex: 2025.2 para 2025 semestre 2)",
        key="periodo_input"
    )
    
    if periodo_input:
        if validar_periodo(periodo_input):
            periodos_formatados = [periodo_input.replace('.', '')]
            st.success(f"✅ Período válido: {periodo_input}")
        else:
            st.error("❌ Formato inválido. Use AAAA.S (ex: 2025.2)")
            periodos_formatados = []
    else:
        periodos_formatados = []
    
    # Permitir múltiplos períodos
    adicionar_periodo = st.checkbox("Adicionar outro período", key="adicionar_periodo")
    if adicionar_periodo:
        periodo2 = st.text_input("Segundo período:", value="2025.1", key="periodo2")
        if periodo2 and validar_periodo(periodo2):
            periodos_formatados.append(periodo2.replace('.', ''))
    
    st.markdown("---")
    st.subheader("🎓 Cursos")
    
    cursos_selecionados = st.multiselect(
        "Selecione os cursos:",
        options=['Química', 'Química Industrial'],
        default=['Química', 'Química Industrial'],
        key="cursos_selecionados"
    )
    
    st.markdown("---")
    st.subheader("🏫 Departamentos")
    
    # Opção para digitar departamento livremente
    modo_departamento = st.radio(
        "Modo de seleção de departamento:",
        options=['Lista pré-definida', 'Digitar código'],
        key="modo_departamento"
    )
    
    departamentos_selecionados = []
    
    if modo_departamento == 'Lista pré-definida':
        # Departamentos comuns
        departamentos_opcoes = [
            'TODOS', 'GQI', 'GFI', 'MAF', 'FIS', 'BIO', 'MAT', 
            'GEC', 'GEO', 'GEA', 'GFB', 'GCN', 'GCO'
        ]
        
        departamentos_selecionados = st.multiselect(
            "Selecione departamentos:",
            options=departamentos_opcoes,
            default=['TODOS'],
            key="departamentos_lista"
        )
    else:
        # Entrada livre
        depto_input = st.text_input(
            "Digite o código do departamento (3 letras):",
            value="GQI",
            max_chars=3,
            help="Ex: GQI, MAF, FIS, BIO, etc.",
            key="depto_input"
        )
        
        if depto_input:
            depto_input = depto_input.strip().upper()
            if validar_departamento(depto_input):
                departamentos_selecionados = [depto_input]
                st.success(f"✅ Departamento válido: {depto_input}")
            else:
                st.error("❌ Código inválido. Use 3 letras (ex: GQI) ou 'TODOS'")
                departamentos_selecionados = []
        else:
            departamentos_selecionados = ['TODOS']
    
    st.markdown("---")
    
    # Configurações avançadas
    with st.expander("⚙️ Configurações Avançadas"):
        st.session_state.apenas_cursos_quimica = st.checkbox(
            "Mostrar apenas cursos de Química", 
            value=True,
            help="Filtrar para mostrar apenas vagas dos cursos 028 (Química) e 029 (Química Industrial)",
            key="apenas_cursos_quimica"
        )
        
        st.checkbox("Usar cache", value=True, help="Usar cache para consultas repetidas", key="usar_cache")
        st.checkbox("Detalhar todas as turmas", value=True, help="Extrair dados detalhados de cada turma", key="detalhar_turmas")
        limite_turmas = st.number_input("Limite de turmas por consulta", min_value=10, max_value=500, value=100, key="limite_turmas")
    
    st.markdown("---")
    
    # Botões de ação
    col1, col2 = st.columns(2)
    
    with col1:
        btn_consultar = st.button("🔍 Consultar Vagas", 
                                 type="primary", 
                                 use_container_width=True,
                                 disabled=not periodos_formatados or not cursos_selecionados,
                                 key="btn_consultar")
    
    with col2:
        if st.button("🔄 Limpar", use_container_width=True, key="btn_limpar"):
            st.session_state.processando = False
            st.session_state.resultado_disponivel = False
            st.session_state.dados_turmas = None
            st.rerun()
    
    st.markdown("---")
    st.info("""
    **💡 Informações:**
    - A consulta detalhada pode levar alguns minutos
    - Cada período é processado separadamente
    - Os dados são extraídos em tempo real do sistema UFF
    """)

# Área de teste de extração individual
testar_extracao_individual()

# Área principal - Processamento
if btn_consultar and periodos_formatados and cursos_selecionados:
    st.session_state.processando = True
    st.session_state.resultado_disponivel = False
    
    with st.spinner("🔄 Inicializando consulta..."):
        try:
            # Configurar consultor com filtro
            apenas_quimica = st.session_state.get('apenas_cursos_quimica', True)
            consultor = ConsultorQuadroHorariosUFFDetalhado(apenas_cursos_quimica=apenas_quimica)
            
            # Preparar departamentos para consulta
            deptos_consulta = []
            for depto in departamentos_selecionados:
                if depto == 'TODOS':
                    deptos_consulta.append(None)
                else:
                    deptos_consulta.append(depto)
            
            # Se não há departamentos selecionados, usar todos
            if not deptos_consulta:
                deptos_consulta = [None]
            
            st.info(f"""
            **🎯 Consulta Configurada:**
            - 📅 Períodos: {', '.join([formatar_periodo(p) for p in periodos_formatados])}
            - 🎓 Cursos: {', '.join(cursos_selecionados)}
            - 🏫 Departamentos: {', '.join([d if d else 'Todos' for d in departamentos_selecionados])}
            - 🔍 Filtro: {'Apenas cursos de Química' if apenas_quimica else 'Todos os cursos'}
            """)
            
            st.warning("""
            ⚠️ **Atenção:** Esta consulta pode levar vários minutos dependendo do número de turmas.
            Por favor, não feche esta página durante o processamento.
            """)
            
            # Executar consulta
            dados = consultor.consultar_vagas_completas(
                periodos=periodos_formatados,
                cursos=cursos_selecionados,
                departamentos=deptos_consulta
            )
            
            if dados:
                df_resultado = pd.DataFrame(dados)
                st.session_state.dados_turmas = df_resultado
                st.session_state.resultado_disponivel = True
                st.session_state.processando = False
                
                st.success(f"✅ Consulta concluída com sucesso!")
                st.success(f"📊 {len(dados)} registros coletados")
                
                # Mostrar estatísticas
                col_stat1, col_stat2, col_stat3 = st.columns(3)
                with col_stat1:
                    st.metric("Cursos encontrados", len(df_resultado['curso_vaga'].unique()))
                with col_stat2:
                    st.metric("Departamentos", len(df_resultado['departamento'].unique()))
                with col_stat3:
                    st.metric("Turmas com vagas", len(df_resultado[df_resultado['total_vagas_disponiveis'] > 0]))
                
                # Mostrar preview
                with st.expander("👁️ Visualizar amostra dos dados"):
                    st.dataframe(df_resultado.head(10), use_container_width=True)
                
                st.rerun()
            else:
                st.error("❌ Nenhuma turma encontrada com os filtros selecionados.")
                st.session_state.processando = False
        
        except Exception as e:
            st.error(f"❌ Erro durante a consulta: {str(e)}")
            st.exception(e)
            st.session_state.processando = False

# Área principal - Resultados
if st.session_state.resultado_disponivel and st.session_state.dados_turmas is not None:
    df = st.session_state.dados_turmas
    
    st.markdown("---")
    st.subheader("📋 Resultados da Consulta")
    
    # Mostrar período formatado
    periodo_formatado = formatar_periodo(periodos_formatados[0] if periodos_formatados else "")
    
    # Estatísticas rápidas
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Período", periodo_formatado)
    
    with col2:
        st.metric("Total de Turmas", len(df))
    
    with col3:
        turmas_vagas = len(df[df['total_vagas_disponiveis'] > 0])
        st.metric("Turmas com Vagas", turmas_vagas)
    
    with col4:
        total_vagas_disp = df['total_vagas_disponiveis'].sum()
        st.metric("Vagas Disponíveis", total_vagas_disp)
    
    # Visualizações
    criar_visualizacoes(df)
    
    # Exportação
    st.markdown("---")
    st.subheader("📥 Exportar Resultados")
    
    col_exp1, col_exp2, col_exp3 = st.columns(3)
    
    with col_exp1:
        # Exportar Excel Completo
        if st.button("📊 Excel Completo", use_container_width=True, key="btn_excel"):
            excel_buffer = gerar_excel_completo(df, periodo_formatado)
            if excel_buffer:
                st.download_button(
                    label="⬇️ Baixar Excel Completo",
                    data=excel_buffer,
                    file_name=f"vagas_uff_detalhado_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
    
    with col_exp2:
        # Exportar CSV
        if st.button("📄 CSV Simples", use_container_width=True, key="btn_csv"):
            csv = df.to_csv(index=False, encoding='utf-8-sig')
            st.download_button(
                label="⬇️ Baixar CSV",
                data=csv,
                file_name=f"vagas_uff_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
                use_container_width=True
            )
    
    with col_exp3:
        # Exportar JSON
        if st.button("🔤 JSON", use_container_width=True, key="btn_json"):
            json_data = df.to_json(orient='records', indent=2, force_ascii=False)
            st.download_button(
                label="⬇️ Baixar JSON",
                data=json_data,
                file_name=f"vagas_uff_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                mime="application/json",
                use_container_width=True
            )
    
    # Tabela interativa completa
    st.markdown("---")
    st.subheader("📋 Tabela Completa de Dados")
    
    # Filtros interativos
    col_filt1, col_filt2, col_filt3 = st.columns(3)
    
    with col_filt1:
        filtro_curso = st.selectbox(
            "Filtrar por curso:",
            options=['Todos'] + list(df['curso_vaga'].unique()),
            key="filtro_curso_tabela"
        )
    
    with col_filt2:
        filtro_depto = st.selectbox(
            "Filtrar por departamento:",
            options=['Todos'] + [d for d in df['departamento'].unique() if pd.notna(d)],
            key="filtro_depto_tabela"
        )
    
    with col_filt3:
        filtro_vagas = st.selectbox(
            "Filtrar por vagas:",
            options=['Todas', 'Com vagas disponíveis', 'Sem vagas'],
            key="filtro_vagas_tabela"
        )
    
    # Aplicar filtros
    df_filtrado = df.copy()
    
    if filtro_curso != 'Todos':
        df_filtrado = df_filtrado[df_filtrado['curso_vaga'] == filtro_curso]
    
    if filtro_depto != 'Todos':
        df_filtrado = df_filtrado[df_filtrado['departamento'] == filtro_depto]
    
    if filtro_vagas == 'Com vagas disponíveis':
        df_filtrado = df_filtrado[df_filtrado['total_vagas_disponiveis'] > 0]
    elif filtro_vagas == 'Sem vagas':
        df_filtrado = df_filtrado[df_filtrado['total_vagas_disponiveis'] == 0]
    
    # Mostrar tabela
    st.dataframe(
        df_filtrado[[
            'periodo', 'departamento', 'codigo_disciplina', 'nome_disciplina', 
            'turma', 'curso_vaga', 'vagas_reg', 'inscritos_reg', 'vagas_disponiveis_reg',
            'vagas_vest', 'inscritos_vest', 'vagas_disponiveis_vest', 'total_vagas_disponiveis'
        ]],
        column_config={
            "periodo": "Período",
            "departamento": "Depto",
            "codigo_disciplina": "Código",
            "nome_disciplina": "Disciplina",
            "turma": "Turma",
            "curso_vaga": "Curso",
            "vagas_reg": "Vagas Reg",
            "inscritos_reg": "Inscritos Reg",
            "vagas_disponiveis_reg": "Disp. Reg",
            "vagas_vest": "Vagas Vest",
            "inscritos_vest": "Inscritos Vest",
            "vagas_disponiveis_vest": "Disp. Vest",
            "total_vagas_disponiveis": "Total Disp."
        },
        hide_index=True,
        use_container_width=True,
        height=400
    )
    
    st.info(f"Mostrando {len(df_filtrado)} de {len(df)} registros")

# Página inicial
elif not st.session_state.processando:
    st.markdown("---")
    
    col_intro1, col_intro2 = st.columns([2, 1])
    
    with col_intro1:
        st.markdown("""
        ## 🎯 Sistema de Consulta de Vagas UFF
        
        Este sistema consulta **detalhadamente** as vagas disponíveis nas disciplinas do 
        **Instituto de Química da UFF**, extraindo informações completas de cada turma.
        
        ### 📋 **Funcionalidades:**
        
        **✅ Consulta Sem Duplicação:**
        - Dados únicos por turma e curso
        - Filtro para mostrar apenas cursos de Química
        - Evita registros duplicados
        
        **✅ Departamentos Flexíveis:**
        - Lista pré-definida ou digitação livre
        - Aceita qualquer código de 3 letras
        - Retorna mensagem clara se não houver resultados
        
        **✅ Exportação Completa:**
        - Excel com múltiplas abas (igual ao Colab)
        - Formatação profissional com cores
        - Estatísticas detalhadas
        - Dados brutos em CSV/JSON
        
        ### 🎓 **Cursos Suportados:**
        - 🧪 **Bacharelado em Química** (Código 028)
        - 🏭 **Bacharelado em Química Industrial** (Código 029)
        """)
    
    with col_intro2:
        st.markdown("""
        ## ⚙️ **Como Usar:**
        
        1. **📅 Digite o período** (ex: 2026.1)
        2. **🎓 Selecione os cursos**
        3. **🏫 Escolha departamentos** (lista ou digite)
        4. **⚙️ Configure filtros** (apenas Química, etc.)
        5. **🔍 Clique em Consultar Vagas**
        6. **📊 Analise os resultados**
        7. **📥 Exporte os dados**
        
        ## ⚠️ **Importante:**
        
        - ⏳ Consultas detalhadas são mais lentas
        - 📶 Conexão estável necessária
        - 🔄 Não feche durante o processamento
        - ✅ Use o teste individual primeiro
        
        ## 🆘 **Suporte:**
        
        Em caso de problemas:
        - Use a função de teste individual
        - Verifique o formato do período
        - Tente menos filtros inicialmente
        - Digite códigos de departamento manualmente
        """)
    
    # Exemplo de dados
    with st.expander("📋 **Exemplo de Dados Coletados**"):
        st.markdown("""
        | Campo | Descrição | Exemplo |
        |-------|-----------|---------|
        | **periodo** | Período letivo | 20252 |
        | **departamento** | Código do departamento | GQI |
        | **codigo_disciplina** | Código da disciplina | GQI0001 |
        | **nome_disciplina** | Nome da disciplina | Química Geral |
        | **turma** | Identificação da turma | A01 |
        | **horarios** | Horários das aulas | Segunda: 08-10h \| Quarta: 10-12h |
        | **curso_vaga** | Curso da vaga | 028 - Química |
        | **vagas_reg** | Vagas regulares | 40 |
        | **inscritos_reg** | Inscritos regulares | 35 |
        | **vagas_disponiveis_reg** | Vagas disp. regulares | 5 |
        | **vagas_vest** | Vagas vestibular | 20 |
        | **inscritos_vest** | Inscritos vestibular | 18 |
        | **vagas_disponiveis_vest** | Vagas disp. vestibular | 2 |
        | **total_vagas_disponiveis** | Total vagas disponíveis | 7 |
        """)

# Rodapé
st.markdown("---")
st.markdown(
    "<div style='text-align: center; color: #666; font-size: 0.9rem;'>"
    "🧪 **Consultor de Vagas UFF - Instituto de Química** • "
    "Desenvolvido por **Tadeu L. Araújo (GGQ)** • "
    f"Versão: {datetime.now().strftime('%d/%m/%Y')}"
    "</div>",
    unsafe_allow_html=True
)
