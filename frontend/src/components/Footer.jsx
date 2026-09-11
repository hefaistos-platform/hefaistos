import React from 'react';
import './Footer.css';

const Footer = () => {
  const currentYear = new Date().getFullYear();
  
  return (
    <footer className="hefaistos-footer">
      <div className="footer-content">
        <div className="footer-section">
          <h4>HEFAISTOS</h4>
          <p>Detection Engineering Platform</p>
        </div>
        
        <div className="footer-section">
          <h4>Documentation</h4>
          <ul>
            <li><a href="/docs">Guides</a></li>
            <li><a href="/api">API</a></li>
            <li><a href="/github">GitHub</a></li>
          </ul>
        </div>
        
        <div className="footer-section copyright">
          <p>&copy; 2025-2026 Jan Pohl - m3c4n1sm0 and multiple AI bots</p>
          <p>All rights reserved.</p>
        </div>
      </div>
    </footer>
  );
};

export default Footer;
