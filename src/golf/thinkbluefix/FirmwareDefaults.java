package golf.thinkbluefix;

import de.vw.mib.asl.framework.api.diagnosis.config.EcoHmi;

/** Keeps native defaults when the selected profile receives the reviewed blank configuration. */
public final class FirmwareDefaults implements EcoHmi {
    private static final String STD2_CONFIG =
            "de.vw.mib.asl.framework.internal.diagnosis.variant.std2.EcoHmiImpl";
    private static final int CONFIG_LENGTH = 102;
    private static final int FIRST_OVERRIDE = 747;
    private static final int LAST_OVERRIDE = 838;

    private final EcoHmi source;

    private FirmwareDefaults(EcoHmi source) {
        this.source = source;
    }

    public static EcoHmi preserve(EcoHmi source, int engineType, int gearType) {
        if (source == null || !SelectedProfile.matches(engineType, gearType)
                || !STD2_CONFIG.equals(source.getClass().getName())) {
            return source;
        }

        byte[] raw = source.getRawData();
        if (raw == null || raw.length != CONFIG_LENGTH) {
            return source;
        }
        for (int index = 0; index < raw.length; index++) {
            if (raw[index] != 0) {
                return source;
            }
        }
        for (int id = FIRST_OVERRIDE; id <= LAST_OVERRIDE; id++) {
            if (!source.contains(id)) {
                return source;
            }
        }
        return new FirmwareDefaults(source);
    }

    public boolean contains(int id) {
        return (id < FIRST_OVERRIDE || id > LAST_OVERRIDE) && source.contains(id);
    }

    public int getValue(int id) {
        return source.getValue(id);
    }

    public boolean getBoolean(int id) {
        return source.getBoolean(id);
    }

    public byte[] getByteArray(int id) {
        return source.getByteArray(id);
    }

    public byte[] getRawData() {
        return source.getRawData();
    }
}
