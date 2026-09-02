import { Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import AuditPage from "./features/audit/AuditPage";
import ChatPage from "./features/chat/ChatPage";
import ConsentPage from "./features/consent/ConsentPage";
import PipelinePage from "./features/control-plane/PipelinePage";
import MerchantPage from "./features/merchant/MerchantPage";
import SimulatorPage from "./features/policy-simulator/SimulatorPage";
import SecurityPage from "./features/security/SecurityPage";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<ChatPage />} />
        <Route path="/consent" element={<ConsentPage />} />
        <Route path="/pipeline" element={<PipelinePage />} />
        <Route path="/simulate" element={<SimulatorPage />} />
        <Route path="/audit" element={<AuditPage />} />
        <Route path="/security" element={<SecurityPage />} />
        <Route path="/merchant" element={<MerchantPage />} />
      </Route>
    </Routes>
  );
}
