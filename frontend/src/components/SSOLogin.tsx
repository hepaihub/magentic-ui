import React from "react";

const backgroundStyle: React.CSSProperties = {
  minHeight: "100vh",
  display: "flex",
  justifyContent: "center",
  alignItems: "center",
  margin: 0,
  background: `linear-gradient(rgba(0,0,0,0.5), rgba(0,0,0,0.5)),
    url('https://images.unsplash.com/photo-1497864149936-d3163f0c0f4b?ixlib=rb-1.2.1&auto=format&fit=crop&w=1950&q=80')`,
  backgroundSize: "cover",
  backgroundPosition: "center",
  fontFamily: "Arial, sans-serif",
  position: "relative",
};

const logoContainerStyle: React.CSSProperties = {
  position: "fixed",
  top: 20,
  left: 20,
  zIndex: 1000,
  color: "white",
  fontSize: 16,
  lineHeight: 1.2,
};

const containerStyle: React.CSSProperties = {
  textAlign: "center",
  padding: "2rem",
  background: "rgba(255,255,255,0.1)",
  borderRadius: 15,
  backdropFilter: "blur(10px)",
  boxShadow: "0 8px 32px 0 rgba(31, 38, 135, 0.37)",
};

const h1Style: React.CSSProperties = {
  color: "#fff",
  fontSize: "2.5rem",
  marginBottom: "1.5rem",
  textShadow: "2px 2px 4px rgba(0,0,0,0.5)",
};

const h2Style: React.CSSProperties = {
  color: "#fff",
  fontSize: "1.5rem",
  marginBottom: "1.5rem",
  textShadow: "2px 2px 4px rgba(0,0,0,0.5)",
};

const buttonStyle: React.CSSProperties = {
  padding: "15px 30px",
  fontSize: "1.1rem",
  background: "rgba(255,255,255,0.1)",
  color: "#fff",
  border: "none",
  borderRadius: 25,
  cursor: "pointer",
  transition: "all 0.3s ease",
  backdropFilter: "blur(5px)",
  boxShadow: "0 4px 15px rgba(0,0,0,0.2)",
};

const buttonHoverStyle: React.CSSProperties = {
  background: "rgba(255,255,255,0.2)",
  transform: "translateY(-2px)",
  boxShadow: "0 6px 20px rgba(0,0,0,0.3)",
};

export const SSOLogin: React.FC = () => {
  const [hover, setHover] = React.useState(false);

  const handleLogin = () => {
    window.location.href = "/umt/login";
  };

  return (
    <div style={backgroundStyle}>
      <div style={logoContainerStyle}>
          IHEP计算中心&实验物理中心
      </div>
      <div style={containerStyle}>
        <h2 style={h2Style}>欢迎探索 Dr. Sai 智能体</h2>
        <button
          style={hover ? { ...buttonStyle, ...buttonHoverStyle } : buttonStyle}
          onMouseEnter={() => setHover(true)}
          onMouseLeave={() => setHover(false)}
          onClick={handleLogin}
        >
          使用高能所统一认证（IHEP-SSO）登录
        </button>
      </div>
    </div>
  );
};

export default SSOLogin;
