import { useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Button } from '@/components/ui/button';
import { useUpdateCharger } from '@/api/chargers';
import { toast } from 'sonner';
import { OCPP_VERSIONS, type ChargerDetailResponse } from '@/types/ocpp';

const chargerDetailsSchema = z.object({
  connection_url: z.string().url('Must be a valid URL').min(1, 'Connection URL is required'),
  charger_name: z.string().min(1, 'Charger name is required'),
  ocpp_version: z.enum(['1.6', '2.0.1']),
});

type ChargerDetailsFormValues = z.infer<typeof chargerDetailsSchema>;

interface ChargerDetailsEditProps {
  charger: ChargerDetailResponse;
  locationId: string;
}

export function ChargerDetailsEdit({ charger, locationId }: ChargerDetailsEditProps) {
  const updateCharger = useUpdateCharger(locationId);
  const form = useForm<ChargerDetailsFormValues>({
    resolver: zodResolver(chargerDetailsSchema),
    defaultValues: {
      connection_url: charger.connection_url,
      charger_name: charger.charger_name,
      ocpp_version: OCPP_VERSIONS.includes(charger.ocpp_version as (typeof OCPP_VERSIONS)[number])
        ? charger.ocpp_version
        : '1.6',
    },
  });

  useEffect(() => {
    form.reset({
      connection_url: charger.connection_url,
      charger_name: charger.charger_name,
      ocpp_version: OCPP_VERSIONS.includes(charger.ocpp_version as (typeof OCPP_VERSIONS)[number])
        ? charger.ocpp_version
        : '1.6',
    });
  }, [charger.connection_url, charger.charger_name, charger.ocpp_version]); // form omitted to avoid loop

  const hasChanges =
    form.watch('connection_url') !== charger.connection_url ||
    form.watch('charger_name') !== charger.charger_name ||
    form.watch('ocpp_version') !== charger.ocpp_version;

  async function onSubmit(values: ChargerDetailsFormValues) {
    try {
      await updateCharger.mutateAsync({
        chargePointId: charger.charge_point_id,
        payload: values,
      });
      toast.success('Charger updated');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to update charger');
    }
  }

  return (
    <Card className="bg-card border-border">
      <CardHeader className="pb-3">
        <CardTitle className="text-base font-medium">Charger Details</CardTitle>
        <p className="text-sm text-muted-foreground">
          Edit connection URL, name, and OCPP version. Charge point ID is read-only.
        </p>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="py-2 px-3 bg-secondary/50 rounded-lg">
          <p className="text-xs text-muted-foreground mb-1">Charge point ID</p>
          <p className="font-mono text-sm">{charger.charge_point_id}</p>
        </div>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <FormField
              control={form.control}
              name="connection_url"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Connection URL</FormLabel>
                  <FormControl>
                    <Input placeholder="wss://csms.example.com/ocpp/CP001" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="charger_name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Charger name</FormLabel>
                  <FormControl>
                    <Input placeholder="e.g. Charger A1" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="ocpp_version"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>OCPP version</FormLabel>
                  <Select onValueChange={field.onChange} value={field.value}>
                    <FormControl>
                      <SelectTrigger>
                        <SelectValue placeholder="Select OCPP version" />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      {OCPP_VERSIONS.map((v) => (
                        <SelectItem key={v} value={v}>
                          {v}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <FormMessage />
                </FormItem>
              )}
            />
            <Button type="submit" disabled={!hasChanges || updateCharger.isPending}>
              {updateCharger.isPending ? 'Saving…' : 'Save changes'}
            </Button>
          </form>
        </Form>
      </CardContent>
    </Card>
  );
}
