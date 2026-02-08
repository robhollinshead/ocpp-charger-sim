import { useState, useRef } from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { useImportChargers, getChargersCsvTemplateUrl, getChargersJsonTemplateUrl } from '@/api/import';
import { toast } from 'sonner';

interface ImportChargersModalProps {
  locationId: string | undefined;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ImportChargersModal({
  locationId,
  open,
  onOpenChange,
}: ImportChargersModalProps) {
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<{ success: unknown[]; failed: { row: unknown; error: string }[] } | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const importChargers = useImportChargers(locationId);

  function handleClose(open: boolean) {
    if (!open) {
      setFile(null);
      setResult(null);
      onOpenChange(false);
    }
  }

  async function handleSubmit() {
    if (!locationId || !file) return;
    try {
      const data = await importChargers.mutateAsync(file);
      setResult({ success: data.success, failed: data.failed });
      const total = data.success.length + data.failed.length;
      if (data.failed.length === 0) {
        toast.success(`Imported ${data.success.length} charger${data.success.length === 1 ? '' : 's'}`);
      } else {
        toast.info(`${data.success.length} imported, ${data.failed.length} failed`);
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Import failed');
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Import chargers</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-muted-foreground">
          Upload a CSV or JSON file. Format is auto-detected from the file.
        </p>
        <div className="flex flex-wrap gap-2 items-center">
          <Button
            type="button"
            variant="outline"
            size="sm"
            asChild
          >
            <a href={getChargersCsvTemplateUrl()} download="chargers.csv">
              Download CSV template
            </a>
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            asChild
          >
            <a href={getChargersJsonTemplateUrl()} download="chargers.json">
              Download JSON template
            </a>
          </Button>
        </div>
        <div className="flex gap-2 items-center">
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv,.json"
            className="text-sm file:mr-2 file:py-2 file:px-4 file:rounded-md file:border-0 file:bg-primary file:text-primary-foreground"
            onChange={(e) => {
              const f = e.target.files?.[0];
              setFile(f ?? null);
              setResult(null);
            }}
          />
          <Button
            onClick={handleSubmit}
            disabled={!file || !locationId || importChargers.isPending}
          >
            {importChargers.isPending ? 'Importing…' : 'Import'}
          </Button>
        </div>

        {result && (
          <div className="space-y-4 border-t pt-4">
            <p className="text-sm font-medium">
              {result.success.length} imported, {result.failed.length} failed
            </p>
            {result.success.length > 0 && (
              <div>
                <p className="text-sm text-muted-foreground mb-1">Imported</p>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>charge_point_id</TableHead>
                      <TableHead>charger_name</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {(result.success as { charge_point_id?: string; charger_name?: string }[]).map((row, i) => (
                      <TableRow key={i}>
                        <TableCell>{row.charge_point_id ?? '-'}</TableCell>
                        <TableCell>{row.charger_name ?? '-'}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
            {result.failed.length > 0 && (
              <div>
                <p className="text-sm text-destructive font-medium mb-1">Failed</p>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Error</TableHead>
                      <TableHead>Row</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {result.failed.map((item, i) => (
                      <TableRow key={i}>
                        <TableCell className="text-destructive">{item.error}</TableCell>
                        <TableCell className="max-w-[200px] truncate font-mono text-xs">
                          {JSON.stringify(item.row)}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => handleClose(false)}>
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
