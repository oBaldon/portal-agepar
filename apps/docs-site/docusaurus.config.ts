// @ts-check
import { themes as prismThemes } from 'prism-react-renderer';
import type { Config } from '@docusaurus/types';
import type * as Preset from '@docusaurus/preset-classic';

// Este arquivo roda em Node.js — não use APIs de browser aqui.

const config: Config = {
  title: 'Plataforma AGEPAR — Dev Docs',
  tagline: 'Documentação para desenvolvedores da Plataforma AGEPAR',
  favicon: 'img/favicon.ico',

  // Flags de futuro — ver https://docusaurus.io/docs/api/docusaurus-config#future
  future: {
    v4: true,
  },

  // URL pública base do site (ajuste em produção, se necessário)
  url: 'http://localhost',
  // Caminho base onde o site será servido (via proxy do Host em /devdocs)
  baseUrl: '/devdocs/',

  // Config de repositório (ajuste conforme seu Git)
  organizationName: 'oBaldon',
  projectName: 'portal-agepar',

  // Continua válido no v3 (apenas o onBrokenMarkdownLinks mudou)
  onBrokenLinks: 'throw',

  // Internacionalização
  i18n: {
    defaultLocale: 'pt-BR',
    locales: ['pt-BR'],
  },

  presets: [
    [
      'classic',
      {
        docs: {
          // use require.resolve para garantir resolução do caminho no Node
          sidebarPath: require.resolve('./sidebars.ts'),
          // Link "editar esta página"
          editUrl: 'https://github.com/oBaldon/portal-agepar/tree/main/apps/docs-site/',
        },
        blog: {
          showReadingTime: true,
          routeBasePath: '/blog',
          include: ['**/*.{md,mdx}'],
          exclude: ['**/_*.{md,mdx}', '**/README.{md,mdx}'], // ⬅️ ignora README
          editUrl: 'https://github.com/oBaldon/portal-agepar/tree/main/apps/docs-site/',
          onInlineTags: 'warn',
          onInlineAuthors: 'warn',
          onUntruncatedBlogPosts: 'warn',
        },
        theme: {
          // idem: resolução via Node
          customCss: require.resolve('./src/css/custom.css'),
        },
      } satisfies Preset.Options,
    ],
  ],

  // Temas e configurações visuais
  themes: ['@docusaurus/theme-mermaid', '@docusaurus/theme-live-codeblock'],
  markdown: {
    mermaid: true,
    hooks: {
      // substitui o antigo onBrokenMarkdownLinks na raiz do config
      onBrokenMarkdownLinks: 'warn',
    },
  },

  themeConfig: {
    // Playground: onde o preview aparece em relação ao código
    liveCodeBlock: {
      playgroundPosition: 'bottom' // 'top' | 'bottom'
    },
    image: 'img/docusaurus-social-card.jpg',
    colorMode: {
      respectPrefersColorScheme: true,
    },
    navbar: {
      title: 'Plataforma AGEPAR',
      logo: {
        alt: 'Logo da Plataforma AGEPAR',
        src: 'img/logo.svg',
      },
      items: [
        {
          type: 'docSidebar',
          sidebarId: 'techSidebar',
          position: 'left',
          label: 'Docs',
        },
        { to: '/blog', label: 'Blog', position: 'left' },
        {
          href: 'https://github.com/oBaldon/portal-agepar',
          label: 'GitHub',
          position: 'right',
        },
      ],
    },
    footer: {
      style: 'dark',
      links: [
        {
          title: 'Docs',
          items: [{ label: 'Introdução', to: '/docs/intro' }],
        },
        {
          title: 'Comunidade',
          items: [
            { label: 'Stack Overflow', href: 'https://stackoverflow.com/questions/tagged/docusaurus' },
            { label: 'Discord', href: 'https://discordapp.com/invite/docusaurus' },
            { label: 'X (Twitter)', href: 'https://x.com/docusaurus' },
          ],
        },
        {
          title: 'Mais',
          items: [
            { label: 'Blog', to: '/blog' },
            { label: 'GitHub', href: 'https://github.com/oBaldon/portal-agepar' },
          ],
        },
      ],
      copyright: `Copyright © ${new Date().getFullYear()} Plataforma AGEPAR.
      Construído com Docusaurus.`,
    },
    prism: {
      theme: prismThemes.github,
      darkTheme: prismThemes.dracula,
      // (opcional) garanta TSX e outros idiomas no highlight
      additionalLanguages: ['tsx', 'typescript', 'jsx', 'bash', 'json', 'diff'],
    },
  } satisfies Preset.ThemeConfig,
};

export default config;
