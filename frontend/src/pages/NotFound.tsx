import { Compass } from "lucide-react";
import { Link } from "react-router-dom";
import { buttonStyles, Card, EmptyState } from "@/components/ui";

export default function NotFound() {
  return (
    <Card>
      <EmptyState
        icon={<Compass className="h-6 w-6" />}
        title="Page not found"
        action={
          <Link to="/" className={buttonStyles("primary")}>Go to Home</Link>
        }
      >
        That address isn't part of the Coop Platform.
      </EmptyState>
    </Card>
  );
}
