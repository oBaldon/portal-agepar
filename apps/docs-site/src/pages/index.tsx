// apps/docs-site/src/pages/index.tsx
import type { ReactNode } from 'react';
import Link from '@docusaurus/Link';
import Layout from '@theme/Layout';
import useDocusaurusContext from '@docusaurus/useDocusaurusContext';
import styles from './index.module.css';

function Hero() {
  const { siteConfig } = useDocusaurusContext();
  return (
    <header className={styles.hero}>
      <div className={`container ${styles.heroInner}`}>
        <div className={styles.heroLeft}>
          <h1 className={styles.title}>Portal AGEPAR — Dev Docs</h1>
          <p className={styles.subtitle}>
            BFF (FastAPI), Host (React/Vite/TS), Catálogo modular, Automações e Docs.
          </p>

          <div className={styles.ctaRow}>
            <Link className={`button button--primary ${styles.cta}`} to="/docs/intro">
              🚀 Começar pela Introdução
            </Link>
            <Link className={`button button--secondary ${styles.cta}`} to="/docs/visão-geral-e-arquitetura">
              🧭 Visão Geral & Arquitetura
            </Link>
          </div>

          <div className={styles.meta}>
            <span>Dev stack:</span>
            <ul>
              <li>Host: Vite + React/TypeScript</li>
              <li>BFF: FastAPI (Pydantic v2, SQLite)</li>
              <li>Docs: Docusaurus + Mermaid</li>
            </ul>
          </div>
        </div>

        <div className={styles.heroRight}>
          <div className={styles.codeCard}>
            <div className={styles.codeHeader}>docker compose</div>
            <pre className={styles.codeBlock}>
{`services:
  host:
    build: ./apps/host
    ports: ["5173:5173"]
  bff:
    build: ./apps/bff
    ports: ["8000:8000"]`}
            </pre>
            <div className={styles.codeFooter}>
              <code>docker compose up --build</code>
            </div>
          </div>
        </div>
      </div>
    </header>
  );
}

function FeatureGrid() {
  const cards = [
    {
      title: 'Frontend (Host)',
      desc: 'Navbar por categorias, leitura do catálogo e RBAC simples.',
      to: '/docs/frontend-host-react-vite-ts',
    },
    {
      title: 'BFF (FastAPI)',
      desc: 'Rotas /api, validação Pydantic v2, normalização e erros claros.',
      to: '/docs/bff-fastapi',
    },
    {
      title: 'Automações',
      desc: 'Módulos isolados com UI via iframe e endpoints padrão.',
      to: '/docs/automations-padrão-de-módulos',
    },
    {
      title: 'Catálogo',
      desc: 'Estrutura JSON, categories/blocks e convenções.',
      to: '/docs/catálogo-catalog-dev',
    },
    {
      title: 'Segurança',
      desc: 'CORS restrito, cookies de sessão e superfícies públicas.',
      to: '/docs/segurança',
    },
    {
      title: 'Observabilidade',
      desc: 'Padrões de log, contexto em exceptions e métricas.',
      to: '/docs/observabilidade',
    },
    {
      title: 'Testes',
      desc: 'cURL/pytest, Vitest e roteiros manuais.',
      to: '/docs/testes',
    },
    {
      title: 'Docusaurus',
      desc: 'Estrutura das docs, snippets e diagramas.',
      to: '/docs/documentação-docusaurus',
    },
  ];

  return (
    <section className="container margin-vert--lg">
      <div className={styles.grid}>
        {cards.map((c) => (
          <Link key={c.title} to={c.to} className={styles.card}>
            <h3>{c.title}</h3>
            <p>{c.desc}</p>
            <span className={styles.cardLink}>Abrir seção →</span>
          </Link>
        ))}
      </div>
    </section>
  );
}

export default function Home(): ReactNode {
  return (
    <Layout title="Portal AGEPAR — Dev Docs" description="Documentação técnica do Portal AGEPAR">
      <Hero />
      <FeatureGrid />
    </Layout>
  );
}
