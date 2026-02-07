import { Location } from '@/types/ocpp';
import { MapPin, Zap } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Card, CardContent } from '@/components/ui/card';

interface LocationCardProps {
  location: Location;
}

export function LocationCard({ location }: LocationCardProps) {
  return (
    <Link to={`/location/${location.id}`}>
      <Card className="bg-card border-border hover:border-primary/50 hover:bg-card/80 transition-all cursor-pointer group">
        <CardContent className="p-5">
          <div className="flex items-start justify-between">
            <div className="flex-1">
              <h3 className="font-semibold text-foreground group-hover:text-primary transition-colors">
                {location.name}
              </h3>
              <div className="flex items-center gap-1.5 mt-2 text-sm text-muted-foreground">
                <MapPin className="h-3.5 w-3.5" />
                {location.address}
              </div>
            </div>
            <div className="flex items-center gap-1.5 px-3 py-1.5 bg-secondary rounded-lg">
              <Zap className="h-4 w-4 text-primary" />
              <span className="font-medium text-foreground">{location.chargerCount}</span>
            </div>
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}
