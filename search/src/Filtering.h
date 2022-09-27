/*
 * Filtering.h
 *
 * Created on: Sept 2, 2022
 *
 * Helper functions for filtering results.
 */

#ifndef FILTERING_H_
#define FILTERING_H_

#include <vector>

namespace kbmod {

/* Return the list of indices from the values array such that those elements
   pass the sigmaG filtering defined by percentiles [sGL0, sGL1] with coefficient
   sigmaGCoeff and a multiplicative factor of width. */
std::vector<int> sigmaGFilteredIndices(const std::vector<float>& values,
                                       float sGL0, float sGL1,
                                       float sigmaGCoeff, float width);
    
double calculateLikelihood(std::vector<double> psiValues, std::vector<double> phiValues);
    
std::tuple<std::vector<double>, std::vector<double>> calculateKalmanFlux(std::vector<double> fluxValues, 
                                                                       std::vector<double> invFluxes,
                                                                       std::vector<int> fluxIdx, int pass);
    
std::tuple<std::vector<int>, double> kalmanFilterIndex(std::vector<double> psiCurve,
                                                      std::vector<double> phiCurve);
    
std::vector<std::tuple<int, std::vector<int>, double>> kalmanFiteredIndices(const std::vector<std::vector<double>>& psiValues, 
                                                                            const std::vector<std::vector<double>>& phiValues,
                                                                            int numValues);
} /* namespace kbmod */

#endif /* FILTERING_H_ */
