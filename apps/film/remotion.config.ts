import {Config} from '@remotion/cli/config';

// Frames are JPEG while rendering (faster, no alpha); overlay compositions switch to PNG + ProRes 4444 on the
// command line (see README). Output files are overwritten so a render command can be re-run as is.
Config.setVideoImageFormat('jpeg');
Config.setOverwriteOutput(true);
Config.setConcurrency(4);
