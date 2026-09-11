import React from 'react';
import ReactDOM from 'react-dom/client';
import 'antd/dist/reset.css';
import './index.css';
import App from './App';
import { PlaybookMetaProvider } from './context/PlaybookMetaContext';
import { ThemeProvider, useTheme } from './context/ThemeContext';
import reportWebVitals from './reportWebVitals';
import { ApolloProvider } from '@apollo/client/react'; // CORRECTED IMPORT PATH
import client from './apollo-client';
import { ConfigProvider, theme, App as AntdApp } from 'antd';

const ThemedProviders = () => {
  const { resolvedTheme } = useTheme();
  const isDark = resolvedTheme === 'dark';

  const configTheme = React.useMemo(
    () => ({
      algorithm: isDark ? theme.darkAlgorithm : theme.defaultAlgorithm,
      token: {
        colorPrimary: '#1677ff',
        colorLink: '#3b82f6',
        borderRadius: 8,
        colorBgLayout: isDark ? '#0f172a' : '#f5f8fc',
      },
      components: {
        Card: {
          headerBg: isDark ? '#13233d' : '#e6f2ff',
          padding: 16,
        },
        Tag: {
          defaultBg: isDark ? '#102a4a' : '#e6f4ff',
          defaultColor: isDark ? '#93c5fd' : '#0958d9',
        },
        Layout: {
          headerBg: isDark ? '#0b1220' : '#f5f8fc',
          bodyBg: isDark ? '#0f172a' : '#f9fbfd',
          siderBg: isDark ? '#0b1220' : '#ffffff',
        },
      },
    }),
    [isDark]
  );

  return (
    <ConfigProvider theme={configTheme}>
      <AntdApp>
        <PlaybookMetaProvider>
          <App />
        </PlaybookMetaProvider>
      </AntdApp>
    </ConfigProvider>
  );
};

const root = ReactDOM.createRoot(
  document.getElementById('root') as HTMLElement
);

root.render(
  <React.StrictMode>
    <ApolloProvider client={client}>
      <ThemeProvider>
        <ThemedProviders />
      </ThemeProvider>
    </ApolloProvider>
  </React.StrictMode>
);

// If you want to start measuring performance in your app, pass a function
// to log results (for example: reportWebVitals(console.log))
// or send to an analytics endpoint. Learn more: https://bit.ly/CRA-vitals
reportWebVitals();
