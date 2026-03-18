
import { Outlet } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { TopNav } from './TopNav';
import { StatusStrip } from './StatusStrip';

export function Shell() {
  return (
    <div className="flex h-screen w-screen bg-background text-foreground overflow-hidden">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden">
        <TopNav />
        <main className="flex-1 overflow-auto bg-background p-6">
          <div className="max-w-[1600px] mx-auto">
            <Outlet />
          </div>
        </main>
        <StatusStrip />
      </div>
    </div>
  );
}
