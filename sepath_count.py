#!/usr/bin/env python2
from sepath_core import *
from itertools import chain
# import re
# import numpy
import optparse
import sys
# import json
import pysam
import HTSeq


def count(cargo, seb, split):
    cargo[seb][split] += 1

def write_bed(se_ga, fn):
    with open(fn, "wb") as fh:
        for iv, ses in se_ga.steps():
            for gene_id, i,j,n in ses:
                seg_id = "%s_%s:%s:%s" % (gene_id, i, j, n)
                fh.write("\t".join(map(str, [iv.chrom, iv.start, iv.end, seg_id, 0, 
                                             iv.strand, "\n"])))

def write_sep(seps_counts, seps_lengths, se_gl, fh):
    fh.write("\t".join(["gene_id", "total", "unique", "contiguous", "sep_length", "sep1", "sep2"]) + "\n")
    for gene_id, ses_counts in seps_counts.iteritems():
        #gene_length = se_gl[gene_id]
        ses_lengths = seps_lengths[gene_id]
        for ses, (total, unique) in ses_counts.iteritems():
            contiguous = ses_lengths[ses][0]
            sep_length = ses_lengths[ses][1]
            #isize      = ses_lengths[ses][2]
            ses1 = "-".join(["%s:%s:%s" % se for se in ses[0]])
            ses2 = "-".join(["%s:%s:%s" % se for se in ses[1]])
            line = "\t".join([gene_id, str(total), str(unique), str(contiguous), str(sep_length), ses1, ses2]
            ) + "\n"
            fh.write(line)

def count_subexonpaths(seps):
    counts = {}
    for gene_id, ses_cargo in seps.iteritems():
        counts[gene_id] = {}
        for ses, cargo in ses_cargo.iteritems():
            total = sum(cargo.values())
            unique = len(cargo.values())
            counts[gene_id][ses] = (total, unique)
    return counts

def measure_subexonpaths(seps, se_gm):
    lengths = {}
    for gene_id, ses_cargo in seps.iteritems():
        lengths[gene_id] = {}
        for ses, cargo in ses_cargo.iteritems():
            ses_lengths = [[(se_gm[(gene_id,) + se]).length for se in sei] for sei in ses]
            try:
                first_left = ses[0][0]
                last_left = ses[0][-1]
                first_right = ses[1][0]
                last_right = ses[1][-1]
                contiguous = (-5 <= first_right[-1] - last_left[-1] <= 1)
                if contiguous:
                    sep_length = sum(set(chain.from_iterable(ses_lengths)))
                    # inserts = [sep_length - (start - se_gm[(gene_id,) + first_left].start) - \
                    #                             (se_gm[(gene_id,) + last_right].end - end) for \
                    #            (chr, start, end, strand), count in cargo.iteritems()]
                    # isize = "%d:%d:%s:%s" % (numpy.mean(inserts), numpy.std(inserts), 
                    #                          min(inserts), max(inserts))
            except IndexError:
                contiguous = False
                sep_length = float("nan")
                #isize = "nan:nan:nan:nan"
            lengths[gene_id][ses] = \
                (
                    contiguous,
                    sep_length,
                    #isize,
                    #ses_lengths
                )
    return lengths


if __name__ == "__main__":

    optParser = optparse.OptionParser( 
        usage = "%prog [options] alignment_file annotation_file",
        
        description = \
        "This script takes a paired-end 'alignment_file' in BAM/SAM format and a" +
        "'annotation_file' in GTF/GFF format and counts how many times a fragment was" +
        "mapped to a specific order of sub-exons a.k.a its sub-exon path",
        
        epilog = \
        "Written by Marcin Cieslik (mcieslik@med.umich.edu) " +
        "Michigan Center for Translational Pathology (c) 2014 " +
        "Built using 'HTSeq' (%s)." % HTSeq.__version__
    )

    optParser.add_option("--stranded", action="store_true", dest="stranded",
                         default=False, help="turn on strand-specific analysis (fr-firststrand)")

    optParser.add_option("--unique", action="store_true", dest="unique",
                         default=False, help="count unique fragments per sub-exon path")

    optParser.add_option("--qc", type="string", dest="qc",
                         default="strict", help="read QC filtering 'strict' or 'loose'")

    optParser.add_option("--out", type="string", dest="out", 
                         help="sub-exon path output file (tsv)"),

    optParser.add_option("--bed", type="string", dest="se_bed",
                         help="derived sub-exon annotation (bed)"),

    optParser.add_option("--bag", type="string", dest="seb_json",
                         help="full sub-exon bag output file (json)"),

    optParser.add_option("--path", type="string", dest="sep_json",
                         help="full sub-exon path output file (json)"),

    optParser.add_option("--eattr", type="string", dest="eattr",
                         default="exon_id", help="GFF attribute to be used as exon id (default, " +
                         "suitable for Ensembl GTF files: exon_id)"),
         
    optParser.add_option("--gattr", type="string", dest="gattr",
                         default="gene_id", help="GFF attribute to be used as gene id (default, " +
                         "suitable for Ensembl GTF files: gene_id)"),

    optParser.add_option("--verbose", action="store_true", dest="verbose",
                          help="run-time messages printed to stderr")

    optParser.add_option("--progress", type="int", dest="progress", default=100000,
                          help="progress on BAM processing printed every n lines")

    if len(sys.argv) == 1:
        optParser.print_help()
        sys.exit(1)

    (opts, args) = optParser.parse_args()
    
    if len(args) != 2:
        optParser.print_help()
        sys.exit(1)


    with pysam.Samfile(args[0]) as sf:
        
        try:
            order = re.search("SO:(.*)", sf.text).groups()[0]
        except Exception, e:
            order = None
        if not order in ("queryname", "coordinate"):
            sys.stderr.write("warning: missing SO SAM header flag. " +\
                             "Alignment_file should be sorted by queryname (better) or coordinate.\n")
    
        sys.stderr.write("info: parsing GTF file\n")
        se_ga, se_gm, se_gl = parse_gtf(args[1], stranded=opts.stranded)

        if opts.se_bed:
            sys.stderr.write("info: writing sub-exon BED file\n")
            write_bed(se_ga, opts.se_bed)

        sys.stderr.write("info: finding unique sub-exons\n")
        se_unique = unique_subexons(se_ga)

        sys.stderr.write("info: processing BAM file\n")
        seb_cargos = scanBAM(sf, se_ga, count, opts.progress, opts.qc, "fragment" if opts.unique else None)

        sys.stderr.write("info: calculating sub-exon paths\n")
        sep_cargos = seb2sep(seb_cargos, se_unique)

        sys.stderr.write("info: counting sub-exon paths\n")
        sep_counts = count_subexonpaths(sep_cargos)
        sep_lengths = measure_subexonpaths(sep_cargos, se_gm)

        sys.stderr.write("info: writing sep file '%s'\n" % opts.out)
        out = open(opts.out, "wb") if opts.out else sys.stdout
        write_sep(sep_counts, sep_lengths, se_gl, out)
