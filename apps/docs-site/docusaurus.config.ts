import { themes as prismThemes } from 'prism-react-renderer';
import type { Config } from '@docusaurus/types';
import type * as Preset from '@docusaurus/preset-classic';

// Este arquivo roda em Node.js — não use APIs de browser aqui.

const config: Config = {
  title: 'Portal AGEPAR — Dev Docs',
  tagline: 'Documentação para desenvolvedores do Portal AGEPAR',
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
          sidebarPath: './sidebars.ts',
          // Link "editar esta página"
          editUrl:
            'https://github.com/oBaldon/portal-agepar/tree/main/apps/docs-site/',
        },
        blog: {
          showReadingTime: true,
          feedOptions: {
            type: ['rss', 'atom'],
            xslt: true,
          },
          editUrl:
            'https://github.com/oBaldon/portal-agepar/tree/main/apps/docs-site/',
          onInlineTags: 'warn',
          onInlineAuthors: 'warn',
          onUntruncatedBlogPosts: 'warn',
        },
        theme: {
          customCss: './src/css/custom.css',
        },
      } satisfies Preset.Options,
    ],
  ],

  // Temas e configurações visuais
  themes: ['@docusaurus/theme-mermaid'],
  markdown: {
    mermaid: true,
    hooks: {
      // substitui o antigo onBrokenMarkdownLinks na raiz do config
      onBrokenMarkdownLinks: 'warn',
    },
  },

  themeConfig: {
    image: 'img/docusaurus-social-card.jpg',
    colorMode: {
      respectPrefersColorScheme: true,
    },
    navbar: {
      title: 'Portal AGEPAR',
      logo: {
        alt: 'Logo do Portal AGEPAR',
        src: 'img/logo.svg',
      },
      items: [
        {
          type: 'docSidebar',
          sidebarId: 'tutorialSidebar',
          position: 'left',
          label: 'Documentação',
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
      copyright: `Copyright © ${new Date().getFullYear()} Portal AGEPAR.
      Construído com Docusaurus.`,
    },
    prism: {
      theme: prismThemes.github,
      darkTheme: prismThemes.dracula,
    },
  } satisfies Preset.ThemeConfig,
};

export default config;
